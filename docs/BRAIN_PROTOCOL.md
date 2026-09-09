# BRAIN Protocol Truth Layer

本项目把协议事实集中在 `wqb_agent/protocol.py`。它只记录当前 client 已使用的 endpoint、请求/响应形状、Retry-After 解析和 capability 证据等级，不把社区猜测升级为官方契约。

## Capability 证据等级

| 等级 | 含义 |
|---|---|
| `OFFICIAL` | 来自平台公开协议或当前项目已采用的稳定官方接口说明 |
| `LIVE_VERIFIED` | 当前账号和环境的真实响应已验证 |
| `FIXTURE_VERIFIED` | 脱敏 fixture 通过结构校验；不代表线上可用 |
| `COMMUNITY_OBSERVED` | 社区观察到的接口，只能 probe/fixture，不能成为生产依赖 |
| `UNKNOWN` | 没有足够证据，必须 fail-closed |

当前官方接口登记：`authentication`、`data_sets`、`data_fields`、`simulations`、已知 progress URL、`users/self/alphas`、`alphas`、`aggregates`、`self_correlation`、`prod_correlation`。

`GET /users/self/alphas` 仅用于有界只读同步，按分页读取用户 Alpha 的 `id`、`status`、`dateCreated` 和 `dateSubmitted`；提交 Alpha 与本日模拟 Alpha 使用同一次刷新触发，按 `America/New_York` 本地日筛选，不写入结果侧车。

字段查重使用 `data_fields` 响应中的平台 `alphaCount`（兼容内部标准化键
`alpha_count`）。查重键必须是 `(dataset_id, field_id)`，不能只用字段名；它表示字段在平台现有 Alpha 中的使用量，是本地不保留
Simulation/Alpha 结果时的唯一字段使用事实源。字段发现命中本地目录或
`fields_cache.json` 时，生产配置仍会对候选数据集发起只读刷新；刷新失败或
缺少 `alphaCount` 保持 `UNKNOWN`，严格模式不进入工厂批次。该刷新不保存
Simulation 结果、Alpha payload 或提交历史。

字段目录按 `America/New_York` 本地日固化为
`platform_field_catalog_YYYYMMDD/manifest.json` 加数据集字段文件。manifest
记录查询范围、抓取时间、字段数量、字段哈希和平台使用量状态；目录只包含
平台字段元数据，不包含 Simulation/Alpha 结果。多数据集发现使用可复现种子做
分层轮询，优先保证配置的 `min_datasets` 覆盖，再按字段评分和随机扰动取样。
当前选择必须在 discovery bundle 中暴露数据集池、顺序、选中数量和拒绝原因。

仅观察登记：`operators`、`alpha_check`、`pnl`。这些接口没有被生产 client 自动调用；只有 capability probe 或脱敏 fixture 可以证明其当前可用性。

Retry-After 支持秒数和 HTTP-date，统一由 `retry_after_seconds()` 解析，并拒绝负数、非有限值和畸形值。429 仍受全局 gate 与预算约束，Simulation POST 的未知结果仍进入 `SUBMIT_UNKNOWN`。

## 脱敏 fixtures

`tests/fixtures/brain/` 只包含结构样例，不包含真实账号、alpha、token、字段目录或平台数据。fixture 验证只能产生 `FIXTURE_VERIFIED`，不能替代 live response。
