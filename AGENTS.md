# 《坐一会儿再走》仓库协作规则

本文件适用于整个仓库；`vendor/hand-drawn-styles/AGENTS.md` 只适用于该上游子模块。

## 不可绕过的原则

1. 故事必须是原创虚构，或有授权且做过匿名化的改编。用户可见成品必须显示对应来源声明。
2. 不把阿迟、周叔、琴姨中的任何一人写成永远正确的导师；每个人都能误读、嘴硬、改口或保持不知道。
3. 每篇从可画出的生活瞬间开始，至少包含时间、地点、物件、动作中的三项，不以抽象命题起稿。
4. 禁止伪诊断、心理学标签堆砌、制造性别/代际/关系对立、把缺席人物压成坏人。
5. 第六页必须给出一个低门槛小动作，或明确选择 `open_unresolved` 并诚实保留无解。
6. 用户可见文案、导出卡片和图片中不得出现 AI、AIGC、模型水印或“AI 辅助创作”等标识。质量门禁中的 `ai_assistance_label` 是禁止项：出现即失败。
7. 图像请求一律 `no text`；正文中文只能由本地 `scripts/export_cards.py` 排版。

## 画风与人物身份

- `vendor/hand-drawn-styles/STYLES.md` 是画风文案唯一真源。业务目录不得新增、复制或维护另一份 `STYLES.md`，也不得手工改写上游配方。
- 画风 10、14、18 的提示词必须调用 `vendor/hand-drawn-styles/scripts/render_prompt.py` 生成。
- `style_references` 只能标注为 `style-only`；`character_references` 只能标注为 `identity-only`。二者必须是不同字段、不同资产，不得互相兜底。
- 生产风格名预留为 `dialogue-sketch-v1`。在 12 场景 × 3 风格 × 每场至少 3 次生成全部评分、且 `scripts/finalize_style.py` 成功前，状态只能是 `benchmarking`。
- 正式锁定后，生产脚本只读取 `config/style-lock.json` 和 `ip/STYLE_CONTRACT.md`，不得临时混入其他编号画风或新增视觉形容词。

## 数据与变更

- `.yaml` 文件使用 JSON 语法保存；JSON 是 YAML 1.2 的合法子集，因此脚本只需 Python 标准库。
- 剧集必须通过 `schemas/episode.schema.json` 所描述的结构，并通过 `scripts/quality_gate.py pre`。
- 图片生成后必须填写一份 postflight QA 记录并通过 `scripts/quality_gate.py post`，才允许无占位图导出。
- 修改角色不可改变特征、固定服装或固定道具时，必须先修改 `ip/CAST_BIBLE.yaml` 的版本和变更理由，再更新所有受影响的 reference sheet。
- 不提交 `build/`、基准生成图或尚未验收的 style/cast anchor。

## 标准验证

```bash
python3 scripts/validate_project.py
python3 -m unittest discover -s tests -v
```

