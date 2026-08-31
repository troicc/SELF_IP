# Identity-only 角色参考图规范

基准测试的三种候选画风必须使用同一套中性角色参考图，不能为每种风格各做一套 cast sheet。否则候选画风与角色参考图一起变化，评分无法判断差异来自哪里。

## 文件

- `reference-assets/identity-neutral/achi.png`
- `reference-assets/identity-neutral/zhoushu.png`
- `reference-assets/identity-neutral/qinyi.png`
- `reference-assets/identity-neutral/pair-achi-zhoushu.png`
- `reference-assets/identity-neutral/pair-achi-qinyi.png`
- `reference-assets/identity-neutral/cast-trio.png`（三人同框调用的运输 pack，不是新的身份真源）

五张维护 sheet 与一张 transport pack 的角色覆盖、尺寸、验收状态及 SHA-256 统一记录在 `reference-assets/identity-neutral/manifest.json`。替换图片必须同步更新清单并重新运行标准验证，不能静默换图。

当前六张图片均已通过身份参考目检，36 份标准请求均为 `ready_for_generation: true`。这里的“就绪”只允许开始 108 张基准生成，不代表任何候选画风已经锁定。

现役资产集为 `2.1.0`：使用无渐变、无光影包装、无写实材质的 `functional_flat_cleanup` 制图处理。它故意不像完成插画，只负责交代脸型、身高、服装、道具和互动距离，避免中性 reference 自己带入通用成品插画气质。

调用端最多接收 5 张参考图。单人/双人场景使用独立 sheet 与对应双人 sheet；三人场景使用 `cast-trio.png` 加两张双人 sheet，因此连同一张 `style-only` anchor 也不超过 4 张。pack 只能由三张独立 sheet 维护，不得反向修改角色身份。

## 单人 sheet

每张使用同一浅中性底，不带场景，不出现文字、编号、箭头、logo 或候选画风视觉元素。画面依次包含正面全身、四分之三全身、侧面、三种表情和固定道具近景。身份事实逐项来自 `ip/CAST_BIBLE.yaml`；不得顺手美化、换衣或补充新饰品。

## 双人 sheet

两人并排站在同一基准线，另加一次坐姿与一次简单递物动作。重点锁定相对身高、肩宽、头型差和自然互动距离；不做剧情海报，不使用候选 10/14/18 的配方。

## 调用角色

这些图在所有请求中只能标注：

```json
{"role": "identity-only"}
```

它们只回答“阿迟、周叔、琴姨是谁”。候选画风仍由独立的 `style-only` reference 与上游 style id 控制。若调用端不能分别传递两类引用，基准测试停止，不能把其中一类删掉继续生成。
