# 唯一画风合同：dialogue-sketch-v1

> 当前状态：`benchmarking`  
> 合同版本：`1.0.0`  
> 生产风格名：`dialogue-sketch-v1`（已预留，尚未绑定候选编号）

本文件是业务项目唯一的画风合同。它只规定依赖、资产职责、锁定流程和调用边界，不复制任何画风配方。完整配方唯一来自 `vendor/hand-drawn-styles/STYLES.md`。

## 候选集

| style id | 上游别名 | 只读 style reference | 当前用途 |
| --- | --- | --- | --- |
| 10 | `emo-sketch` | `vendor/hand-drawn-styles/examples/10-emo-sketch.png` | 基准测试 |
| 14 | `nordic-storybook` | `vendor/hand-drawn-styles/examples/14-nordic-storybook.png` | 基准测试 |
| 18 | `warm-flat-storybook` | `vendor/hand-drawn-styles/examples/18-warm-flat-storybook.png` | 基准测试 |

候选提示词必须由上游 `scripts/render_prompt.py` 原样渲染。业务脚本只能提供 style id、主体、上游支持的占位符、`No text` 与 3:4 比例，不得追加线条、五官、色板、材质、纸面或阴影描述。

## 当前证据状态

- 初轮 v1 已完成 12 场景 × 3 风格 × 3 次，共 108 次生成和逐图客观 QA；九项检查全部通过才计成功。风格 10、14、18 的严格成功数分别为 6/36、10/36、7/36。
- B03、B07、B09、B11 在初轮后因生活动作或道具归属被修订。旧 PNG 的提示词哈希分别固定在 `benchmarks/contracts/*-initial-v1.json`，不得改写成当前 prompt；新生成只读取当前 `benchmarks/scenes.yaml`。
- 项目方明确偏好风格 14。基于这一偏好建立的 style-14 v2 专项复测完成 36 次，客观成功 27/36（75%），通过该轮 72% 的生成硬门。
- 专项复测仍暴露四类失败：B08 远处长椅漏画，B10 湿眼与单侧嘴角笑未成立，B11 三种笑趋同，B12 没有真正回头看。
- EP-003 七页校准试播已完成插画、postflight 与本地中文排版。这证明生产链路可运行，不构成主观六项评分，也不能反向锁定风格。
- `benchmarks/scorecard.csv` 仍缺两名真实独立评审的主观分。因此状态必须保持 `benchmarking`，`config/style-lock.json` 不得出现。

## 两类参考图必须分离

```text
style_references      -> role: style-only    -> 只回答“怎么画”
character_references  -> role: identity-only -> 只回答“画的是谁”
```

- 两类引用在请求 JSON 中使用不同字段，不能指向同一文件。
- style anchor 不允许提供角色姓名、固定服装或剧情身份；调用时明确“不复制参考图人物、衣服、站位和情节”。
- cast reference 不承担补救画风的职责；换画风时角色身份约束仍由 `CAST_BIBLE.yaml` 与 cast sheet 提供。
- 任一正式资产缺失、哈希不符或角色标注错误，生产请求失败关闭，不降级为纯文字猜测。

## 基准门

锁定前必须同时满足：

1. 12 个 `benchmarks/scenes.yaml` 场景在 10、14、18 三种风格下全部生成；
2. 每个“场景 × 风格”至少独立生成 3 次，不挑一张代替统计；
3. 36 行评分都填写人物一致性、情绪表达、留白、互动自然度、生成成功率、辨识度；
4. 每种风格至少由两名评审独立评分，分歧超过 1.5 分的项目复核；
5. 人物一致性、生成成功率任一均分低于 3.5/5 的候选直接淘汰；
6. 仅在上述硬门后比较加权总分，不能因单张图好看手工指定赢家。

权重与计算见 `benchmarks/SCORING_RUBRIC.md`。`scripts/finalize_style.py` 会拒绝不完整评分表。

## 冻结后的资产合同

锁定命令成功后，`config/style-lock.json` 必须包含：

- `production_name: dialogue-sketch-v1`；
- 唯一 `upstream_style_id`（10、14、18 之一）；
- 上游仓库 commit；
- `style-anchor.png` 的像素文件 SHA-256，角色内容仅作反例、不作身份来源；
- 阿迟、周叔、琴姨三张独立 identity reference 的 SHA-256；
- 至少一张阿迟与长辈的双人 cast sheet；本项目同时要求阿迟—周叔、阿迟—琴姨两张；
- 评分摘要、锁定日期、评审人。

冻结后所有生产脚本只读取这一把锁。不得接受命令行 `--style 其他编号`，不得临时混入其他编号、艺术家名、模型风格词或“优化版”画风段落。若要改画风，递增合同版本并重新跑完整基准。

## 画幅与文字安全区

- 卡片统一 3:4，基准坐标使用归一化 `x/y/width/height`（0–1）。
- 图像请求必须保护每页声明的 `reserved_text_regions`；关键脸、手、道具与高对比元素不得进入。
- 图像模型永远不生成正文中文，也不得出现任何可读/伪文字。上游风格 10 明确传 `不加任何文字`；风格 18 传 `No text anywhere.`；风格 14 自带 `No text.`。
- `scripts/export_cards.py` 在本地把中文排进安全区，并把来源声明放在第七页页脚。
- 对复杂主体允许使用 `scripts/place_illustration_stage.py` 做确定性前景落位；它只能移动和缩放已验收前景，不能修补人物、肢体、道具、表情或人数错误。落位前后的图都必须保留各自 QA 记录。

## 内容级 negative constraints

基准请求允许单独携带内容级负向约束：准确角色人数、无额外人物/肢体、固定衣服和道具、不复制 style reference 人物、保护文字安全区、无文字。它们不得包含或改写画风规则，也不得拼进上游 style recipe；调用适配器应把它们作为独立约束字段传递。
