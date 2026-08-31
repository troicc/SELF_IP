# 坐一会儿再走

用固定人物之间的原创手绘对话，陪 23—35 岁成年人把亲情、爱情、友情和自我关系里说不清的话，想清楚一点。

当前仍是 `benchmarking`，但第一阶段系统与可落地试播已经完成：初轮 12 场景 × 3 风格 × 3 次共 108 张均有客观 QA；风格 14 的身份与构图专项复测为 27/36（75%），通过 72% 客观硬门；EP-003 已完成七页插画、postflight 和本地中文排版。风格 14 是当前优先基线，不等于已经锁定 `dialogue-sketch-v1`。两名真实独立评审尚未填写主观六项评分，因此生产锁继续失败关闭，仓库不会伪造评审或用项目方偏好冒充统计结论。

## 第一阶段交付位置

| 交付 | 真源 |
| --- | --- |
| 定位、世界、声音、编辑护栏 | `ip/` |
| 三个角色圣经 | `ip/CAST_BIBLE.yaml` |
| 唯一画风合同 | `ip/STYLE_CONTRACT.md` |
| 12 个标准场景 × 10/14/18 提示词合同 | `benchmarks/scenes.yaml`、`benchmarks/styles.yaml` |
| 108 次初轮客观 QA 与评分表 | `benchmarks/runs/`、`benchmarks/scorecard.csv` |
| 风格 14 专项复测 | `benchmarks/style14-refinement.yaml`、`benchmarks/refinement-runs/style14-v2.json` |
| 12 个完整试播选题 | `topic-bank.csv` |
| 四篇七页试播脚本 | `episodes/EP-001.yaml`—`EP-004.yaml` |
| 模板、脚本、自动化测试 | `templates/`、`scripts/`、`tests/` |

`vendor/hand-drawn-styles/` 是 `threerocks/hand-drawn-styles` 上游 submodule。仓库只保留上游那一份 `STYLES.md`，并保留原 MIT License。业务层不复制也不改写编号画风配方。

`.yaml` 文件使用 JSON 语法保存；JSON 是 YAML 1.2 的合法子集，业务脚本只依赖 Python 3 标准库。确定性画面落位另需本机 `ffmpeg`。

## 初始化与完整验收

```bash
git submodule update --init --recursive
python3 scripts/validate_project.py
python3 -m unittest discover -s tests -v
```

也可以运行：

```bash
make validate
make test
```

验证会检查：业务层只有一份 `STYLE_CONTRACT.md`、上游只有一份 `STYLES.md`、MIT License 与上游 commit 未漂移、三位角色字段完整、identity-only 资产及哈希有效、12 个选题与四篇剧集通过编辑门禁、36 个标准请求可由上游渲染器生成、108 次初轮记录可追溯、风格 14 复测记录为 27/36 且仍未越权锁定。

## 从选题到七张卡片：完整命令

下面是当前校准阶段已经实际跑通的 EP-003 链路。图像模型只接收无正文的 JSONL 请求；正文中文最后由本地 SVG 排版器添加。

```bash
# 1. 选题、文案和生成前门禁
python3 scripts/select_topic.py --topic T003 --out build/work/T003/topic.json
python3 scripts/quality_gate.py pre --episode episodes/EP-003.yaml

# 2. 生成七个风格 14 校准请求
python3 scripts/build_pilot_calibration_jobs.py \
  --episode episodes/EP-003.yaml \
  --out build/pilots/EP-003/jobs.jsonl

# 3. 调用端逐条读取 jobs.jsonl；每张图必须 no text，并按 output_path
#    保存为 build/pilots/EP-003/art-raw/page-01.png … page-07.png

# 4. 把前景确定性放入声明的文字安全区之外
python3 scripts/place_illustration_stage.py \
  --all \
  --jobs build/pilots/EP-003/jobs.jsonl

# 5. 建立并人工填写逐页 postflight；任何 false 都不得导出
python3 scripts/init_postflight.py \
  --episode episodes/EP-003.yaml \
  --out build/pilots/EP-003/postflight.json
python3 scripts/quality_gate.py post \
  --episode episodes/EP-003.yaml \
  --qa build/pilots/EP-003/postflight.json

# 6. 本地叠加中文、页码与第七页原创虚构声明
python3 scripts/export_cards.py \
  --episode episodes/EP-003.yaml \
  --image-dir build/pilots/EP-003/art \
  --qa build/pilots/EP-003/postflight.json \
  --out build/pilots/EP-003/cards
```

当前工作区已经有本轮通过 postflight 的七张 SVG，位置是 `build/pilots/EP-003/cards/`。`build/`、原始生成图和未锁定 anchor 均被忽略，不作为生产资产提交。

只检查版式、不使用正式插画时：

```bash
make pilot TOPIC=T009 EPISODE=EP-001
```

它会输出 `build/cards/EP-001-layout-proof/`。灰色区域只是插画占位，不是成品。

## 正式生产链（风格锁定后）

`scripts/build_episode_image_requests.py` 只读取 `config/style-lock.json` 与 `ip/STYLE_CONTRACT.md`。锁不存在、资产哈希漂移、style 与 cast reference 混用或临时增加画风词时都会失败。

```bash
python3 scripts/select_topic.py --topic T009 --out build/work/T009/topic.json
python3 scripts/quality_gate.py pre --episode episodes/EP-001.yaml
python3 scripts/build_episode_image_requests.py --episode episodes/EP-001.yaml --out build/requests/EP-001.jsonl
python3 scripts/init_postflight.py --episode episodes/EP-001.yaml --out build/qa/EP-001.json
# 按 JSONL 生成 EP-001-p01.png … EP-001-p07.png，并逐页填写 QA
python3 scripts/quality_gate.py post --episode episodes/EP-001.yaml --qa build/qa/EP-001.json
python3 scripts/export_cards.py --episode episodes/EP-001.yaml --image-dir build/images/EP-001 --qa build/qa/EP-001.json --out build/cards/EP-001
```

图像请求中的 `style_references` 全部是 `style-only`，只回答“怎么画”；`character_references` 全部是 `identity-only`，只回答“画的是谁”。两类字段、资产和职责不可互相替代。

## 视觉基准与当前结论

标准请求与 108 个独立 job：

```bash
python3 scripts/render_benchmarks.py --out build/benchmarks/requests.jsonl
python3 scripts/build_benchmark_jobs.py --out build/benchmarks/jobs.jsonl
```

初轮 v1 已完成 108/108 张客观 QA。九项检查全部为 true 才记一次成功，严格成功数为：风格 10 为 6/36，风格 14 为 10/36，风格 18 为 7/36。这个数字主要暴露复杂动作、道具和文字安全区的失败，不替代人物一致性、情绪、留白、互动自然度与辨识度的双人主观评分。

B03、B07、B09、B11 在复盘后被改得更自然或补强了道具归属。旧图对应的提示词哈希没有被篡改，而是封存在 `benchmarks/contracts/*-initial-v1.json`；当前 `benchmarks/scenes.yaml` 只用于新生成。原 B07“鞋尖挡伞”已经整体作废，当前 B07 只有阿迟、坨掉的面、未拆筷子与空椅。

风格 14 专项复测命令：

```bash
python3 scripts/build_style14_refinement_jobs.py --out build/benchmarks/style14-refinement-jobs.jsonl
# 按 output_path 生成 36 张原图后：
python3 scripts/place_illustration_stage.py --all --jobs build/benchmarks/style14-refinement-jobs.jsonl
python3 scripts/refinement_run.py validate --run benchmarks/refinement-runs/style14-v2.json --verify-files
```

专项复测结果是 27/36（75%），通过 72% 客观硬门。仍需重点解决：远处长椅漏画、湿眼与单侧嘴角笑、三人不同笑法、真正的回头视线。不能因为一张图好看就忽略这些失败。

## 双人盲评与风格冻结

两名真实评审必须各自填写 `benchmarks/scorecard.csv` 的六项：人物一致性、情绪表达、留白、互动自然度、生成成功率、辨识度，并记录生成腔否决项。详细锚点见 `benchmarks/SCORING_RUBRIC.md`。

只有评分完整且脚本统计出胜者后，才能运行：

```bash
python3 scripts/finalize_style.py \
  --scorecard benchmarks/scorecard.csv \
  --style-anchor benchmarks/outputs/style-14/B01/accepted-anchor.png \
  --achi-ref benchmarks/reference-assets/identity-neutral/achi.png \
  --zhoushu-ref benchmarks/reference-assets/identity-neutral/zhoushu.png \
  --qinyi-ref benchmarks/reference-assets/identity-neutral/qinyi.png \
  --pair-achi-zhoushu benchmarks/reference-assets/identity-neutral/pair-achi-zhoushu.png \
  --pair-achi-qinyi benchmarks/reference-assets/identity-neutral/pair-achi-qinyi.png \
  --reviewers "真实评审甲,真实评审乙"
```

示例 anchor 必须替换成最终统计胜出风格的合格原图；若统计胜者不是 14，脚本会拒绝。成功后才会生成 `config/style-lock.json`、冻结 `dialogue-sketch-v1` 与五张 cast 资产。后续脚本没有临时 `--style` 入口。

## 文案生产法

每篇先写四句，不从封面金句起稿：

1. 刚才具体发生了什么；
2. 阿迟真正不敢说什么；
3. 缺席的人可能怎样理解；
4. 今天能原样发出的最小一句是什么。

再按 2 → 6 → 3/5 → 1/4/7 的顺序写七页。第 4 页只是重新命名，不是标准答案；第 5 页必须允许反驳；第 6 页给十分钟内能做的小动作或明确保留无解；第 7 页只记录做完以后真实留下的状态。

EP-003 的重要句不是“你值得被重视”，而是可直接发送的：`下次有变，能在我出门前说一声吗？`。它有具体对象、时间边界和一点关系成本，也没有替缺席朋友定罪。

每个视觉页只保留一个现实里本来就会发生的主动作。不得为了象征关系而用脚挡物、推拉道具、让多人同时伸手，也不得凭空增加朋友的碗、人物或餐具。完整规则见 `ip/EDITORIAL_GUARDRAILS.md` 与 `ip/VOICE_BIBLE.md`。

## 常用命令

```bash
# 四篇脚本生成前门禁
python3 scripts/quality_gate.py pre --all

# 从 12 个选题中读取一条
python3 scripts/select_topic.py --topic T003

# 同步初轮客观成功数到评分表
python3 scripts/sync_scorecard_counts.py

# 验证风格 14 专项复测记录（本地有原图时加 --verify-files）
python3 scripts/refinement_run.py validate --run benchmarks/refinement-runs/style14-v2.json

# 完整项目验收
make validate
make test
```

用户可见卡片只显示故事来源声明，不显示制作工具、模型名、水印或相关辅助创作标识。图像模型不直接生成正文中文。
