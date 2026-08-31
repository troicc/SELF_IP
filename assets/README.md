# 固定镜头资产

人物身份参考位于 `assets/references/`。它们只用于固定阿迟与周叔的外形，不再驱动逐页复杂动作。

正式生产只需要四张长期复用的镜头，放入 `assets/plates/`：

- `quiet.png`
- `achi-talk.png`
- `zhoushu-talk.png`
- `together.png`

建议规格：1600×1200 PNG，4:3，纯暖白背景或透明背景。

每张只画阿迟和周叔的胸像或半身：

- 不画家具和完整房间；
- 不画完整腿脚；
- 手尽量留在裁切范围之外；
- 不画手机界面、文字、气泡或招牌；
- 不增加第三个人；
- 不依赖复杂道具说明情绪。

先执行：

```bash
python3 scripts/build.py episodes/EP-001.json
```

四条镜头请求会写入 `build/EP-001/prompts.jsonl`。四张镜头一旦满意就长期复用，不要每篇重新生成人物。
