# FieldDiscovery Scaling Design

## Goal

扩展现有 `FieldDiscovery`，让 dataset 与 field 数量增长时仍有可审计的分页边界、分层检索和透明排序证据，同时保持 Alpha Factory template semantics、Simulation 安全入口和现有研究状态 owner 不变。

## Scope and invariants

- 只修改 `wqb_agent.discovery.FieldDiscovery`、必要的 metadata catalog manifest 读取/写入逻辑和 discovery tests。
- 不新增 field state、trajectory、ledger、checkpoint 或 research state。
- `DATASET_CATEGORIES` 保留为 seed/fallback；已存在的 read-only `client.get_datasets()` 可作为动态 dataset universe 来源。
- discovery artifact 只允许包含 field metadata、分页完整性、scope、usage provenance 和 ranking provenance，不得包含 Simulation metrics/results、Alpha payload 或 submission state。
- `target_count` 仍是 Agent active fields 数量；内部 candidate pool 独立受有界上限控制。

## Pagination completeness contract

每次从 BRAIN 拉取一个 dataset 的一个 `FIELD_TYPES` 成员时，记录：

```json
{
  "expected_count": 1201,
  "loaded_count": 1201,
  "complete": true,
  "truncation_reason": null
}
```

`expected_count` 必须来自平台 `count`，且为非负整数；所有分页的 count 必须一致。`complete=true` 只允许在以下条件同时成立时出现：count 有效、每页响应是 list、分页前进、累计有效返回达到 count，或收到合法空尾页且累计数量等于 count。达到 `max_pages`、count 缺失/变化、返回 malformed、分页不前进或返回数量超过 count 时，`complete=false`，并使用稳定的 `truncation_reason`（例如 `MAX_PAGES`, `MISSING_COUNT`, `COUNT_CHANGED`, `MALFORMED_PAGE`, `NON_PROGRESS`, `COUNT_UNDERRUN`）。

MATRIX 与 VECTOR 各自记录，dataset/catalog provenance 同时暴露两类状态以及聚合状态。未完整的数据不能被描述为 complete catalog；不完整结果仍可作为当前 discovery 的有限候选，但持久化快照必须带 INCOMPLETE/TRUNCATED provenance。

## Dataset universe boundary

若 client 提供 callable `get_datasets()`，FieldDiscovery 以其只读返回值归一化 dataset IDs，作为非显式 dataset scope 的动态候选池；调用失败、返回 malformed 或能力不存在时，明确记录 fallback 并使用 `DATASET_CATEGORIES`、`dataset_pool`。不新增客户端远端能力，也不把 seed 列表伪装为完整平台 universe。

## Layered retrieval and ranking

字段 metadata 仍按 bounded pagination 拉入当前 catalog/cache；排序前先做 cheap candidate retrieval，每个 dataset 只保留固定有界的候选（默认 100），再执行现有语义分数、coverage、alphaCount penalty 与 deterministic random exploration 的组合排序。active output 仍由 `target_count` 控制，stratified round-robin 仍按 dataset 维持覆盖。

每个输出 profile 的 `ranking_provenance` 至少包含：

- `keyword_contribution`
- `coverage_contribution`
- `alpha_count_penalty`
- `random_exploration_contribution`

`match_score` 保留为兼容汇总分数；这些字段只解释 selection，不改变 Factory template 或经济语义。

## Hypothesis tokens

token extraction 使用本地 regex：保留英文/数字 token，并将中文连续片段拆成稳定的 2--4 字 n-gram（同时保留长度足够的完整片段），结合中英文 stopwords 去重并限长。不使用 embedding、网络服务或隐式远端分词。

## Compatibility and fail-closed loading

新 manifest 写入 completeness、catalog status、universe provenance 和 scope。读取 catalog 时必须校验 manifest/dataset payload 结构与 scope；不完整或旧格式快照不得被标记为 COMPLETE。scope mismatch 继续拒绝复用，malformed catalog 继续回退 BRAIN API。

## Verification

回归测试覆盖：超过 1000 fields/type、platform count 大于 loaded、达到 max_pages、malformed pagination、中文 token、多 dataset stratified sampling、scope mismatch，以及 catalog artifact 不包含 metrics/results。
