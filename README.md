# 坐一会儿再走

一个双人手绘对话 IP：阿迟说出那些卡在嘴边的话，周叔不替他下结论，只陪他把问题缩成下一步。

当前版本把全部普通对白统一为一套专业漫画气泡：平滑 soft-TV 轮廓、统一暖白填充、统一靛蓝描边、统一短尾和居中文字。人物与文字不再上下分区，尾巴沿人物嘴部方向建立归属。

## 当前旗舰样稿

> 我妈摔了一跤。第一个知道的是邻居。我三天后才知道。

故事的关键不在于指责妈妈隐瞒，而在第三页：阿迟想起她以前打来时，自己总说“妈，我在开会”。最后没有强行和解，只落实到一个动作——晚上八点，他提前拨了过去。

## 一条命令

```bash
python3 scripts/build.py episodes/EP-001.json
```

输出：

```text
build/EP-001/
├── prompts.jsonl
├── cards/              # 5 张 1080×1440 SVG
├── caption.txt
└── manifest.json
```

## 气泡系统

- 所有普通对白使用同一个 `soft-tv-standard` 样式。
- 文字居中，人工换行尽量形成上短、中宽、下短的文本块。
- 尾巴指向人物嘴部的隐形方向线，但不会扎进脸。
- 尾巴默认走约 56% 距离，并限制最大可见长度，避免细长针状尾巴。
- 角色归属由尾巴完成，不在气泡里重复写人物名。
- 只有真正重要的一句允许加轻微珊瑚色下划线，气泡本身不换造型。

完整约定见 [`ip/BALLOON_BIBLE.md`](ip/BALLOON_BIBLE.md)。

## 对话系统

每篇五页：

1. 一个具体的关系反差；
2. 当事人真正听到的原话；
3. 一个能重新理解前文的新信息；
4. 一句现在可以做或说的话；
5. 一个不完全回应和可见行动。

详细规则见 [`ip/DIALOGUE_BIBLE.md`](ip/DIALOGUE_BIBLE.md)。

## 人物图

四张固定透明 PNG：

```text
assets/plates/quiet.png
assets/plates/achi-talk.png
assets/plates/zhoushu-talk.png
assets/plates/together.png
```

图像模型只画人物和淡彩，不生成文字、气泡、家具、完整房间、复杂手部和第三个人。

## 字体

字体栈优先调用：

```text
LXGW WenKai Medium
LXGW WenKai
霞鹜文楷
```

正文使用 600，重点使用 700，并加入轻微同色描边以改善手机阅读。字体文件不提交到仓库；本机未安装时退回系统楷体。

## 新建一篇

复制 `episodes/EP-001.json`，修改对白与气泡槽位：

```bash
cp episodes/EP-001.json episodes/EP-002.json
python3 scripts/build.py episodes/EP-002.json
```

## 验证

```bash
python3 -m unittest discover -s tests -v
```
