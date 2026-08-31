# 坐一会儿再走

一个简单的双人手绘对话 IP：**阿迟把没说出口的话说出来，周叔帮他把问题拆小一点。**

这个仓库只做三件事：

1. 用五页讲完一个具体、容易共鸣的小故事；
2. 复用两个固定人物和四个固定半身镜头；
3. 把正文排成干净的 3:4 卡片，不让文字粗暴盖在图片上。

插画是内容载体，不是电影分镜。前 30 篇不生成完整房间、餐桌走位、复杂手势、手机界面和多人道具连续性。

## 一条命令

```bash
python3 scripts/build.py episodes/EP-001.json
```

输出：

```text
build/EP-001/
├── prompts.jsonl        # 四张固定镜头的生成请求；满意后长期复用
├── cards/               # 五张 SVG 卡片
├── caption.txt          # 发布文案
└── manifest.json
```

四张固定镜头放在：

```text
assets/plates/quiet.png
assets/plates/achi-talk.png
assets/plates/zhoushu-talk.png
assets/plates/together.png
```

没有插画时，程序只导出明确标注的版式证明，不拿劣质图冒充成品。

## 五页结构

1. **问题**：一句具体钩子；
2. **事实**：刚才发生了什么；
3. **感受**：真正介意的是什么；
4. **表达**：一句现实中能直接说出口的话；
5. **结果**：人物做了什么，只落一层道理。

一篇最多两个角色、一个事实冲突、一个重要句子。周叔不是万能导师，也可以判断错、改口或不知道。

## 新建一篇

```bash
cp episodes/EP-001.json episodes/EP-002.json
# 修改 episode_id、文案与四种固定镜头的选择
python3 scripts/build.py episodes/EP-002.json
```

## 导出 PNG

SVG 是排版真源。需要 PNG 时安装 CairoSVG 后运行：

```bash
python3 -m pip install cairosvg
python3 scripts/build.py episodes/EP-001.json --png
```

## 验证

```bash
make test
```

人物、内容和视觉规则分别见：

- `ip/IP_BIBLE.md`
- `visual/plates.json`
- `AGENTS.md`
