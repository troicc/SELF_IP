# 坐一会儿再走

一个很简单的双人手绘对话 IP：**阿迟把没说出口的话说出来，周叔帮他把问题拆小一点。**

这个仓库只做三件事：

1. 写一个五页、能看完的小故事；
2. 复用固定人物与固定镜头，不为每页编排复杂动作；
3. 把正文排成干净的 3:4 卡片。

不再做 108 张基准图、三风格竞赛、逐物件 QA、FFmpeg 前景裁切和七页场景连续性。插画是内容的载体，不是电影分镜。

## 最小工作流

```bash
python3 scripts/build.py episodes/EP-001.json
```

输出：

```text
build/EP-001/
├── prompts.jsonl        # 只为缺失的固定镜头生成插画
├── cards/               # 五张 SVG 卡片
├── caption.txt          # 发布文案
└── manifest.json
```

把生成好的固定镜头放入：

```text
assets/plates/quiet.png
assets/plates/achi-talk.png
assets/plates/zhoushu-talk.png
assets/plates/together.png
```

再次执行同一条命令，卡片会自动嵌入真实插画。没有图片时只输出明确标注的版式证明，不伪装成成品。

## 内容结构

每篇严格五页：

1. **钩子**：一个具体问题；
2. **发生了什么**：不讲大道理；
3. **真正介意什么**：把情绪说准；
4. **能怎么开口**：给一句现实中可直接使用的话；
5. **落点**：故事有结果，道理只说一层。

一篇最多两个角色、一个场景事实、一个重要句子。视觉只使用四种固定半身镜头；不生成餐桌、椅子、多人走位、复杂手势、手机界面或道具连续性。

## 新建一篇

复制 `episodes/EP-001.json`，只改文字和所用镜头。不要改角色造型和画风。

```bash
cp episodes/EP-001.json episodes/EP-002.json
python3 scripts/build.py episodes/EP-002.json
```

## 验证

```bash
python3 -m unittest discover -s tests -v
```

## 视觉原则

- 温暖白纸背景；
- 靛蓝松线与很淡的水彩；
- 珊瑚橙只作一个小记忆点；
- 人物只画胸像或半身；
- 表情靠目光、嘴角和头部角度，不靠复杂动作；
- 图像模型不得生成任何文字、气泡、家具和第三个人。

具体规则见 `ip/IP_BIBLE.md` 与 `visual/plates.json`。
