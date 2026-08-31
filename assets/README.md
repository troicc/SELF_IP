# 固定镜头资产

把四张正式插画放在 `assets/plates/`：

- `quiet.png`
- `achi-talk.png`
- `zhoushu-talk.png`
- `together.png`

建议 1600×1200 PNG，纯暖白背景或透明背景。每张只画阿迟和周叔的胸像/半身，不画家具、完整手部动作和文字。

生成请求由 `python3 scripts/build.py episodes/EP-001.json` 写入 `build/EP-001/prompts.jsonl`。固定镜头一旦满意就复用，不要每篇重新生成人物。

## 人物参考

仓库保留三张 identity reference：

- `assets/references/achi.png`
- `assets/references/zhoushu.png`
- `assets/references/achi-zhoushu.png`

它们只负责固定“是谁”；`visual/plates.json` 负责“怎么画”。四张固定镜头生成完成后，日常剧集不再反复调用图像模型。
