# 固定镜头资产

角色参考图：

- `references/achi.png`
- `references/zhoushu.png`
- `references/achi-zhoushu.png`

正式内容只需四张长期复用的 4:3 插画：

- `plates/quiet.png`
- `plates/achi-talk.png`
- `plates/zhoushu-talk.png`
- `plates/together.png`

建议尺寸 1600×1200。背景使用统一暖白纸色或透明底；人物只画胸像/半身，双手可以在画外。不得画正文、气泡、家具、完整房间和第三个人。

运行 `python3 scripts/build.py episodes/EP-001.json` 后，四张镜头的完整生成请求会写入 `build/EP-001/prompts.jsonl`。镜头一旦满意就固定复用，不要每篇重新生成。
