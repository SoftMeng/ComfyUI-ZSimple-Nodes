"""Shared helpers for SaveImagePlus and SaveTextPlus."""
import json
import os
import time
from pathlib import PurePath


def resolve_subfolder(template: str, *, width: int = 0, height: int = 0) -> str:
    now = time.localtime()
    result = template
    result = result.replace("%date:yyyy-MM-dd%", time.strftime("%Y-%m-%d", now))
    result = result.replace("%date", time.strftime("%Y-%m-%d", now))
    result = result.replace("%year%", str(now.tm_year))
    result = result.replace("%month%", str(now.tm_mon).zfill(2))
    result = result.replace("%day%", str(now.tm_mday).zfill(2))
    result = result.replace("%hour%", str(now.tm_hour).zfill(2))
    result = result.replace("%minute%", str(now.tm_min).zfill(2))
    result = result.replace("%second%", str(now.tm_sec).zfill(2))
    result = result.replace("%width%", str(width))
    result = result.replace("%height%", str(height))
    return result


def resume_counter(folder: str, prefix: str, ext: str) -> int:
    if not os.path.isdir(folder):
        return 1
    needle = f"{prefix}_"
    best = 0
    for name in os.listdir(folder):
        p = PurePath(name)
        if p.suffix.lstrip(".") != ext:
            continue
        if not p.stem.startswith(needle):
            continue
        try:
            n = int(p.stem[len(needle):])
        except ValueError:
            continue
        if n > best:
            best = n
    return best + 1 if best else 1


def workflow_json_from_extra(extra_pnginfo) -> str:
    if extra_pnginfo is None:
        return ""
    workflow_data = extra_pnginfo.get("workflow") or extra_pnginfo.get("prompt")
    if workflow_data is None:
        return ""
    return json.dumps(workflow_data, ensure_ascii=False)
