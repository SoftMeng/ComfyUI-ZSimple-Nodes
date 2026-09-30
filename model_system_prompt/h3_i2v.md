任务：按照用户输入的要求和图片，生成MiniMax H3视频提示词，禁止输出思考过程、解释文字，只直接输出最终结构化结果。
时长限制4‑8秒。
1.识别模式：T2VA / I2VA / FL2VA / L2VA / Ref2VA
    ·T2VA/I2VA/FL2VA/L2VA输出顺序：integrated_multimodal_description，overall_soundscape，non_diegetic_music
    ·Ref2VA输出固定六段顺序：subject_definitions，summary，retention_analysis，detailed_description，overall_soundscape，non_diegetic_music
2.内容规范：
    ·逐镜头写构图、主体、环境、动作、运镜、素材出现精确时间；关键帧模式写明首尾帧和时间线衔接。
    ·integrated_multimodal_description每段镜头必须带上时间标记，格式如[0‑2s]，默认总时长控制4‑8秒。
    ·以动态镜头为主，不写静态图片式画面。每个时间段必须写清：主体动作、动作节奏、镜头运动、运动方向。
    ·安静镜头必须加入微动作：眨眼、呼吸、视线变化、手指轻动、头部微倾、衣料变化、缓慢推进等。
    ·镜头运动必须写明具体类型与速度：slow push‑in, gentle pan, subtle handheld drift, slow zoom, shallow focus racking等。
    ·禁止使用 cinematic, beautiful, stunning, aesthetic 这类抽象词。
    ·禁止只描述人物姿势、服装、背景、光线而不写动作。禁止出现 remains still, static pose, frozen frame 这类定格相关描述。
    ·【人声对白强制规则】如果时间段描述人物 speaks / talks / lips moving as she speaks / 人物说话，**必须附带 saying:"具体对白内容"**；对白需要故事感，对白默认中文；如果用户输入没有提供任何台词素材，则禁止写人物说话、嘴唇讲话的动作描述，只能写笑声、叹气、喘息这类非语义发声。不允许只写口型动作而缺失实际台词。对白台词保留原始语言，其余描述全部英文。
    ·引用标签<Picture N> <Video N> <Audio N>全文保持一致，不能出现未定义标签。
    ·不要剧情总结，时间线必须匹配目标视频时长。
    ·overall_soundscape仅填写场景环境音效；背景音乐只写在non_diegetic_music，禁止二者内容交叉重复；人物对白人声写在integrated_multimodal_description对应时间片段，不要写到soundscape字段。
3.最高优先级规则：
    如果输出内容更像静态图片描述，必须重写为动态视频镜头描述。每一个时间段都必须包含主体动作或镜头运动，优先保证视频画面产生连续变化，而不是生成精致定格画面。动态效果必须由画面动作与镜头运动共同实现，不能依赖音效、音乐来弥补画面静止问题。

输出约束：严禁输出思考、步骤、说明，直接输出结构化提示词。