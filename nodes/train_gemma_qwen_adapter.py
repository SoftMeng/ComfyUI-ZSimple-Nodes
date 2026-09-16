"""Train Gemma4-E2B -> Qwen3-4B feature adapter for Z-Image.

Pipeline (run in one ComfyUI node pass):
  1) Load all .txt prompts from `texts_dir`
  2) Run each prompt through `clip_gemma` (layer_idx set by user) — extract
     last hidden state per token
  3) Run each prompt through `clip_qwen` (same layer_idx) — extract the same
  4) Save per-sample features to cached_features/{idx:05d}.pt
  5) If run_train: train a Perceiver-Resampler + MLP Adapter with MSE loss
     between Gemma and Qwen3 features
  6) Save adapter to gemma_to_zimage_adapter.safetensors

Returns the adapter path. denoising-loss fine-tune is intentionally not
implemented — see CLAUDE.md for the planned follow-up.

All heavy imports (torch / safetensors / comfy_api) are kept at module top
because they are required for the class definition to inherit io.ComfyNode.
If any of them fail at import time, the entire custom_nodes package fails
to load — make sure torch + safetensors are installed in the ComfyUI venv.
"""
import json
from pathlib import Path

import torch
from safetensors.torch import save_file

from comfy_api.latest import io

from ._gemma_adapter_common import DEFAULT_DTYPE as DTYPE
from ._gemma_adapter_common import (
    GEMMA_HIDDEN,
    NUM_LATENTS,
    QWEN_HIDDEN,
    GemmaToZImageAdapter,
)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_TOKENS = 512  # safety cap; prevents malformed 100K-token outputs from inflating cache


def _log(msg: str):
    print(f"[TrainGemmaToQwenAdapter] {msg}", flush=True)


def _format_prompt(text: str, chat_template: str) -> str:
    return chat_template.format(text)


def _lazy_imports():
    """Defer heavy module imports to first execute() call so the class
    definition imports cleanly even if torch / safetensors fail to import
    at custom_nodes discovery time.
    """
    global torch, nn, F, save_file
    if "F" not in globals() or F is None:
        import torch as _t
        import torch.nn as _nn
        import torch.nn.functional as _F
        from safetensors.torch import save_file as _sf
        torch = _t
        nn = _nn
        F = _F
        save_file = _sf


def _encode_clip(clip, wrapped: str):
    _lazy_imports()
    try:
        cond = clip.encode_from_tokens(
            clip.tokenize(wrapped, return_word_ids=False),
            return_dict=True,
        )
    except Exception as ex:
        raise RuntimeError(f"clip encode_from_tokens failed: {type(ex).__name__}: {ex}") from ex

    cond_field = cond["cond"] if isinstance(cond, dict) and "cond" in cond else cond

    def _flatten(obj, depth):
        if depth > 4:
            return []
        if isinstance(obj, torch.Tensor):
            return [obj]
        if isinstance(obj, (list, tuple)):
            out = []
            for x in obj:
                out.extend(_flatten(x, depth + 1))
            return out
        return []

    tensors = _flatten(cond_field, 0)
    emb = next((t for t in tensors if t.dim() >= 3), None)
    if emb is None:
        emb = next((t for t in tensors if t.dim() == 2), None)

    if emb is None:
        shapes = [tuple(t.shape) for t in tensors]
        raise RuntimeError(
            f"no per-token hidden state (dim>=2) in cond['cond']. "
            f"tensors found: {shapes}. cond['cond'] type={type(cond_field).__name__}"
        )

    # Collapse 4D+ → 3D by selecting last along dim 1.
    # Common 4D layout is [B, layer, N, H] (Gemma4 E2B has 36 layers).
    while emb.dim() > 3:
        emb = emb.select(1, -1)

    if emb.dim() == 2:
        emb = emb.unsqueeze(0)

    # Force 2D [N, H]. Batch dim is expected to be 1 (single-prompt tokenize).
    if emb.dim() != 3:
        raise RuntimeError(f"unexpected emb dim={emb.dim()} after collapse, shape={tuple(emb.shape)}")
    if emb.shape[0] != 1:
        raise RuntimeError(f"expected batch=1 from single-prompt tokenize, got shape={tuple(emb.shape)}")
    emb = emb.squeeze(0)

    mask = torch.ones(emb.shape[0], dtype=torch.long, device=emb.device)
    return emb, mask


class FeaturePairDataset(torch.utils.data.Dataset):
    def __init__(self, cache_dir: str, indices):
        self.cache_dir = Path(cache_dir)
        self.indices = indices

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, idx):
        return torch.load(self.cache_dir / f"{idx:05d}.pt", weights_only=False)


def _collate(batch):
    # _pad_stack drops invalid rows but the cache loop saves them anyway; filter here so adapter never sees all-zero noise.
    valid = [i for i, b in enumerate(batch) if b["gemma_mask"].sum().item() > 0]
    if not valid:
        raise RuntimeError("no valid samples in batch (all gemma_mask are zero)")
    g_list = [batch[i]["gemma"] for i in valid]
    q_list = [batch[i]["qwen"] for i in valid]
    gm_list = [batch[i]["gemma_mask"] for i in valid]
    qm_list = [batch[i]["qwen_mask"] for i in valid]
    Lg = max(t.shape[0] for t in g_list)
    Lq = max(t.shape[0] for t in q_list)
    Hg = g_list[0].shape[-1]
    Hq = q_list[0].shape[-1]
    B = len(g_list)
    g = torch.zeros(B, Lg, Hg)
    gm = torch.zeros(B, Lg, dtype=torch.long)
    q = torch.zeros(B, Lq, Hq)
    qm = torch.zeros(B, Lq, dtype=torch.long)
    for i, (gt, qt, gmt, qmt) in enumerate(zip(g_list, q_list, gm_list, qm_list)):
        Lgt = gt.shape[0]
        Lqt = qt.shape[0]
        g[i, :Lgt] = gt
        gm[i, :Lgt] = gmt
        q[i, :Lqt] = qt
        qm[i, :Lqt] = qmt
    return g, gm, q, qm


def _extract_features(clip_gemma, clip_qwen, prompts, chat_template, log_prefix: str):
    feats_g, masks_g, feats_q, masks_q = [], [], [], []
    for i, prompt in enumerate(prompts):
        wrapped = _format_prompt(prompt, chat_template)
        with torch.no_grad():
            emb_g, mask_g = _encode_clip(clip_gemma, wrapped)
            emb_q, mask_q = _encode_clip(clip_qwen, wrapped)
        # Safety cap: drop malformed outputs that inflated cache to 70GB before.
        if emb_g.shape[0] > MAX_TOKENS:
            emb_g = emb_g[:MAX_TOKENS]
            mask_g = mask_g[:MAX_TOKENS]
        if emb_q.shape[0] > MAX_TOKENS:
            emb_q = emb_q[:MAX_TOKENS]
            mask_q = mask_q[:MAX_TOKENS]
        feats_g.append(emb_g.detach().to(torch.float32).cpu())
        masks_g.append(mask_g.detach().cpu())
        feats_q.append(emb_q.detach().to(torch.float32).cpu())
        masks_q.append(mask_q.detach().cpu())
        if (i + 1) % 10 == 0:
            _log(f"  {log_prefix} forward { {i + 1} }/{len(prompts)}")
    return feats_g, masks_g, feats_q, masks_q


def _pad_stack(feats, masks):
    clean_feats, clean_masks = [], []
    for t, m in zip(feats, masks):
        if not isinstance(t, torch.Tensor) or t.dim() != 2 or t.shape[0] == 0:
            continue
        if not isinstance(m, torch.Tensor) or m.dim() != 1 or m.shape[0] != t.shape[0]:
            continue
        clean_feats.append(t)
        clean_masks.append(m)
    if not clean_feats:
        raise RuntimeError("no valid feature rows collected (all CLIP encodes returned empty / non-tensor)")
    max_len = max(t.shape[0] for t in clean_feats)
    hidden = clean_feats[0].shape[-1]
    feat_pad = torch.zeros(len(clean_feats), max_len, hidden, dtype=torch.float32)
    mask_pad = torch.zeros(len(clean_feats), max_len, dtype=torch.long)
    for i, (t, m) in enumerate(zip(clean_feats, clean_masks)):
        L = t.shape[0]
        feat_pad[i, :L] = t
        mask_pad[i, :L] = m
    return feat_pad, mask_pad


def _train_adapter(cache_dir: str, out_path: str, batch_size: int, epochs: int, lr: float, patience: int):
    meta = json.loads(Path(cache_dir, "meta.json").read_text())
    n = meta["num_samples"]
    rng = torch.Generator().manual_seed(0)
    perm = torch.randperm(n, generator=rng).tolist()
    val_n = max(1, n // 10)
    val_idx = perm[:val_n]
    tr_idx = perm[val_n:]
    _log(f"  train={len(tr_idx)} val={len(val_idx)}")

    train_loader = torch.utils.data.DataLoader(
        FeaturePairDataset(cache_dir, tr_idx),
        batch_size=batch_size, shuffle=True, collate_fn=_collate, num_workers=0,
    )
    val_loader = torch.utils.data.DataLoader(
        FeaturePairDataset(cache_dir, val_idx),
        batch_size=batch_size, shuffle=False, collate_fn=_collate, num_workers=0,
    )

    return _run_training(train_loader, val_loader, epochs, lr, patience, out_path)


def _run_training(train_loader, val_loader, epochs, lr, patience, out_path):
    # ComfyUI wraps node execution in torch.inference_mode() (execution.py:751); enable_grad() does not escape it.
    with torch.inference_mode(False):
        adapter = GemmaToZImageAdapter().to(DEVICE, dtype=DTYPE)
        n_params = sum(p.numel() for p in adapter.parameters())
        n_req = sum(p.requires_grad for p in adapter.parameters())
        n_frozen = sum(not p.requires_grad for p in adapter.parameters())
        _log(
            f"  adapter params: {n_params / 1e6:.1f}M  "
            f"grad_enabled={torch.is_grad_enabled()}  "
            f"inf_mode={torch.is_inference_mode_enabled()}  "
            f"req_grad={n_req} frozen={n_frozen}"
        )

        opt = torch.optim.AdamW(adapter.parameters(), lr=lr, weight_decay=0.01)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs * max(1, len(train_loader)))
        cfg_mask_prob = 0.12

        best_val = float("inf")
        no_improve = 0
        for epoch in range(epochs):
            adapter.train()
            tr_loss_sum = tr_n = 0
            for g, gm, q_, qm in train_loader:
                g = g.to(DEVICE, dtype=DTYPE)
                gm = gm.to(DEVICE)
                q_ = q_.to(DEVICE, dtype=DTYPE)
                qm = qm.to(DEVICE)
                if torch.rand(()) < cfg_mask_prob:
                    g = torch.zeros_like(g)
                    gm = torch.zeros_like(gm)
                tok_pred, pool_pred = adapter(g, gm)
                # Float32 MSE: bf16 diff against wide-range target tensors loses signal.
                tgt_pool = (q_ * qm.unsqueeze(-1).float()).sum(dim=1) / qm.float().sum(dim=1, keepdim=True).clamp_min(1.0)
                tgt_pool = tgt_pool.to(pool_pred.dtype)
                diff = pool_pred.float() - tgt_pool.float()
                loss = (diff * diff).mean()
                if tr_n == 0 and epoch == 0:
                    _log(f"  diag: pool.requires_grad={pool_pred.requires_grad} grad_fn={pool_pred.grad_fn is not None}")
                    _log(f"  diag: tgt.requires_grad={tgt_pool.requires_grad} grad_fn={tgt_pool.grad_fn is not None}")
                    _log(f"  diag: loss.requires_grad={loss.requires_grad} grad_fn={loss.grad_fn is not None}")
                    _log(f"  diag: pool stats min={pool_pred.float().min().item():.4f} max={pool_pred.float().max().item():.4f}")
                    _log(f"  diag: tgt stats min={tgt_pool.float().min().item():.4f} max={tgt_pool.float().max().item():.4f}")
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(adapter.parameters(), 1.0)
                opt.step()
                sched.step()
                tr_loss_sum += loss.item()
                tr_n += 1

            adapter.eval()
            val_loss_sum = val_n_seen = 0
            with torch.no_grad():
                for g, gm, q_, qm in val_loader:
                    g = g.to(DEVICE, dtype=DTYPE)
                    gm = gm.to(DEVICE)
                    q_ = q_.to(DEVICE, dtype=DTYPE)
                    qm = qm.to(DEVICE)
                    tok_pred, pool_pred = adapter(g, gm)
                    tgt_pool = (q_ * qm.unsqueeze(-1).float()).sum(dim=1) / qm.float().sum(dim=1, keepdim=True).clamp_min(1.0)
                    tgt_pool = tgt_pool.to(pool_pred.dtype)
                    diff = pool_pred.float() - tgt_pool.float()
                    loss = (diff * diff).mean()
                    val_loss_sum += loss.item()
                    val_n_seen += 1
            val_loss = val_loss_sum / max(1, val_n_seen)
            _log(f"  epoch {epoch + 1}/{epochs}  train_loss={tr_loss_sum / max(1, tr_n):.6f}  val_loss={val_loss:.6f}")
            if val_loss < best_val - 1e-6:
                best_val = val_loss
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    _log(f"  early stop at epoch {epoch + 1}")
                    break

        os_module = __import__("os")
        os_module.makedirs(str(Path(out_path).parent), exist_ok=True)
        state = {k: v.detach().contiguous().to(torch.float32).cpu() for k, v in adapter.state_dict().items()}
        save_file(
            state,
            out_path,
            metadata={
                "format": "comfyui-text-encoder-adapter",
                "in_dim": str(GEMMA_HIDDEN),
                "out_dim": str(QWEN_HIDDEN),
                "num_latents": str(NUM_LATENTS),
                "source_te": "gemma4_e2b_it_int8_convrot",
                "target_te": "qwen_3_4b",
                "phase": "text-align-mse-warmup",
                "denoising_done": "False",
            },
        )
        _log(f"  adapter saved: {out_path}  best_val_loss={best_val:.6f}")
    return out_path


class TrainGemmaToQwenAdapter(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="TrainGemmaToQwenAdapter",
            display_name="Train Gemma→Qwen Adapter (Z-Image)",
            category="ZSimple-Nodes/training",
            search_aliases=["adapter", "Gemma", "Qwen", "Z-Image", "text encoder"],
            description=(
                "Train a Perceiver-Resampler + MLP adapter that maps Gemma4-E2B "
                "hidden states into Qwen3-4B hidden states, so a CLIPLoader-loaded "
                "Gemma4 can drive a Z-Image UNet that normally expects Qwen3 features. "
                "Stage 1: extract per-token features from both CLIPs. "
                "Stage 2: train Adapter with MSE loss and save .safetensors."
            ),
            inputs=[
                io.Clip.Input("clip_gemma", tooltip="Gemma4-TE loaded via CLIPLoader (type=gemma4 / qwen_image)."),
                io.Clip.Input("clip_qwen", tooltip="Z-Image native Qwen3-4B TE."),
                io.String.Input("texts_dir", default="/home/jiaoma/文档/jmapplication/ComfyUI/output/2026-09-16",
                                tooltip="Directory containing prompt .txt files (filename pattern: NNNN.txt)."),
                io.Int.Input("layer_idx", default=-2, min=-3, max=35,
                              tooltip="Hidden-state layer index to extract from both CLIPs. -2 matches Z-Image's ZImageTEModel."),
                io.String.Input("chat_template", multiline=True, default="user\n{}\nassistant\n",
                                tooltip="Wraps each prompt before tokenisation. Must match the prompt format the adapter will see at inference."),
                io.Int.Input("batch_size", default=4, min=1, max=32),
                io.Int.Input("epochs", default=20, min=1, max=200),
                io.Float.Input("lr", default=5e-5, min=1e-6, max=1e-2, step=1e-6),
                io.Int.Input("patience", default=3, min=1, max=10,
                             tooltip="Early-stop patience (val_loss not improving for this many epochs)."),
                io.Boolean.Input("run_train", default=True,
                                  tooltip="On = extract + train (default). Off = extract features only, skip training."),
            ],
            outputs=[
                io.String.Output(display_name="adapter_path"),
            ],
        )

    @classmethod
    def execute(
        cls,
        clip_gemma,
        clip_qwen,
        texts_dir,
        layer_idx,
        chat_template,
        batch_size,
        epochs,
        lr,
        patience,
        run_train,
    ) -> io.NodeOutput:
        texts_dir = (texts_dir or "").strip() or "/home/jiaoma/文档/jmapplication/ComfyUI/output/2026-09-16"
        chat_template = chat_template if chat_template and "{}" in chat_template else "user\n{}\nassistant\n"

        try:
            clip_gemma.layer_idx = layer_idx
        except Exception:
            pass
        try:
            clip_qwen.layer_idx = layer_idx
        except Exception:
            pass

        txt_dir = Path(texts_dir)
        if not txt_dir.is_dir():
            raise ValueError(f"texts_dir does not exist: {texts_dir}")
        txt_files = sorted(txt_dir.glob("*.txt"))
        if not txt_files:
            raise ValueError(f"no .txt files in {texts_dir}")
        prompts = [p.read_text(encoding="utf-8", errors="replace").strip() for p in txt_files]
        names = [p.name for p in txt_files]

        cache_dir = txt_dir.parent / "model-trainer" / "cached_features"
        out_dir = txt_dir.parent / "model-trainer"
        cache_dir.mkdir(parents=True, exist_ok=True)

        import shutil as _shutil_disk
        _disk_free = _shutil_disk.disk_usage(str(cache_dir)).free
        _est_need = max(64 * 1024 * 1024, len(prompts) * 12 * 1024 * 1024)
        if _disk_free < _est_need:
            raise RuntimeError(
                f"insufficient disk space: free={_disk_free // (1024*1024)}MB "
                f"estimated need={_est_need // (1024*1024)}MB "
                f"(free < {len(prompts)} * 12MB); free disk and retry"
            )

        _log(f"=== Stage 1: extract | {len(prompts)} prompts | layer_idx={layer_idx} ===")
        feats_g, masks_g, feats_q, masks_q = _extract_features(
            clip_gemma, clip_qwen, prompts, chat_template, "extract"
        )

        g_pad, g_mask = _pad_stack(feats_g, masks_g)
        q_pad, q_mask = _pad_stack(feats_q, masks_q)
        saved = 0
        failed = []
        for i in range(len(prompts)):
            try:
                torch.save(
                    {
                        "prompt": prompts[i],
                        "name": names[i],
                        "gemma": g_pad[i],
                        "gemma_mask": g_mask[i],
                        "qwen": q_pad[i],
                        "qwen_mask": q_mask[i],
                    },
                    cache_dir / f"{i:05d}.pt",
                )
                saved += 1
            except OSError as ex:
                failed.append((i, prompts[i][:80], str(ex)))
                _log(f"  cache save failed at sample {i}: {ex!r}")
                target = cache_dir / f"{i:05d}.pt"
                if target.exists():
                    try:
                        target.unlink()
                    except OSError:
                        pass

        if failed:
            _disk_free_now = _shutil_disk.disk_usage(str(cache_dir)).free
            raise RuntimeError(
                f"cache extraction aborted: {len(failed)} samples failed to save; "
                f"saved {saved}/{len(prompts)} → {cache_dir}; "
                f"disk free={_disk_free_now // (1024*1024)}MB; "
                f"first failure: {failed[0]}"
            )

        meta = {
            "num_samples": len(prompts),
            "max_len": int(max(g_mask[i].sum().item() for i in range(len(prompts)))),
            "gemma_hidden": GEMMA_HIDDEN,
            "qwen_hidden": QWEN_HIDDEN,
            "layer_idx": layer_idx,
            "chat_template": chat_template,
            "denoising_done": False,
        }
        Path(cache_dir, "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        _log(f"=== extract done. cached {len(prompts)} samples to {cache_dir} ===")

        if not run_train:
            return io.NodeOutput(str(cache_dir / "meta.json"))

        _log(f"=== Stage 2: train | batch={batch_size} epochs={epochs} lr={lr} ===")
        adapter_path = _train_adapter(
            str(cache_dir), str(out_dir / "gemma_to_zimage_adapter.safetensors"),
            batch_size, epochs, lr, patience,
        )
        return io.NodeOutput(adapter_path)