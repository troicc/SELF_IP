# 标准化提示词矩阵

`scenes.yaml` 定义 12 个相同内容场景，`styles.yaml` 只登记候选编号、上游 reference 和上游支持的变量，不含画风配方。完整的 36 份调用记录由下列命令生成：

```bash
python3 scripts/render_benchmarks.py --out build/benchmarks/requests.jsonl
```

每条生成记录都包含：

- `subject`；
- `composition`；
- `style_id` 与上游渲染后的完整 `prompt`；
- 角色为 `style-only` 的 `style_references`；
- 角色为 `identity-only` 的 `character_references`；
- 独立的内容级 `negative_constraints`；
- `aspect_ratio`；
- 归一化坐标的 `reserved_text_regions`；
- 预期生成次数、上游 commit、源场景哈希和参考资产就绪状态。

完整 prompt 是 build artifact，不是第二套画风真源。每次构建都由 vendor 渲染器重新生成；若上游 commit 与 `styles.yaml` 固定值不一致，命令失败。

初轮完成后，B03、B07、B09、B11 的场景合同因自然动作或道具归属而修订。历史初轮 PNG 仍按当时的 job prompt 哈希验证，快照位于 `benchmarks/contracts/*-initial-v1.json`；它们不会被当前 prompt 重新签名。当前矩阵只决定下一次生成。这一分层同时保留实验可追溯性与后续场景质量。

候选 cast reference 的生成与归档位置见 `cast-reference-plan.yaml`。场景请求即使输出成功，只要 identity-only 参考资产缺失也会标记为 `ready_for_generation: false`，正式基准执行必须先补齐这些资产。
