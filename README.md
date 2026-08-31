# 坐一会儿再走

一个刻意做简单的双人手绘对话 IP：阿迟把没说出口的话说出来，周叔帮他把问题拆成一句现实里能说出口的话。

现在每张卡片不再把人物放上面、文字堆下面。对白以手绘气泡出现在人物嘴边，人物、文字和情绪处在同一画面里。

## 一条命令

```bash
python3 scripts/build.py episodes/EP-001.json
```

输出：

```text
build/EP-001/
├── prompts.jsonl
├── cards/              # 五张 1080×1440 SVG
├── caption.txt
└── manifest.json
```

## 五页结构

1. 一个具体问题；
2. 事实和没说完的感受；
3. 一句短问或可见物件，让问题露出来；
4. 把大问题缩成一句可以直接发送的话；
5. 一个不完全的回应和人物下一步动作。

对话不追求句句漂亮。全篇要有短回应、停顿、反问和普通句；周叔不负责宣布人生答案。完整规则见 [`ip/DIALOGUE_BIBLE.md`](ip/DIALOGUE_BIBLE.md)。

## 气泡布局

四张固定透明人物图放在：

```text
assets/plates/quiet.png
assets/plates/achi-talk.png
assets/plates/zhoushu-talk.png
assets/plates/together.png
```

`visual/plates.json` 为每张图记录：

- 阿迟和周叔的嘴边锚点；
- 可用气泡位置；
- 每个位置的宽度和最大高度；
- 生图时必须保留的留白。

构建器会自动生成略有手绘抖动的气泡、弯曲尾巴、人物色签和重点句强调。气泡尾线先绘制，透明人物图后绘制，因此尾巴会自然消失在人物轮廓后面，不会横穿五官。

## 字体

项目使用官方字体家族名：

```text
LXGW WenKai Medium
LXGW WenKai
霞鹜文楷
```

优先调用 Medium 字重；正文按 600、重点按 700 排版，并加入很轻的同色描边，让手机端更稳。字体文件不进入仓库，未安装时会退回系统楷体。

macOS 可从霞鹜文楷官方仓库的 Release 或 `fonts/TTF` 获取 `LXGWWenKai-Medium.ttf`，安装后重新构建即可看到正式字体效果。

## 色彩与画风

限定色板为：暖奶油纸、靛蓝正文、珊瑚橙、淡天蓝、奶黄、薄荷绿和少量淡紫。颜色用于区分说话者和节奏，不把页面做成信息图。

固定人物图只负责角色；气泡和文字由本地 SVG 生成。图像模型不得生成任何文字、气泡、家具、手机界面或第三个人。

## 查看效果

构建完成后直接打开 `build/EP-001/cards/` 中的五张 SVG。用于评审的 PNG 总览可以在本地由 SVG 批量导出；预览素材不作为生产人物资产提交。替换四张固定透明人物图时，剧集文案和气泡布局无需重做。

## 新建一篇

复制示例，只修改文本、镜头和气泡槽位：

```bash
cp episodes/EP-001.json episodes/EP-002.json
python3 scripts/build.py episodes/EP-002.json
```

## 验证

```bash
python3 -m unittest discover -s tests -v
```
