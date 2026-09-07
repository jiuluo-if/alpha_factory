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

当前官方接口登记：`authentication`、`data_sets`、`data_fields`、`simulations`、已知 progress URL、`alphas`、`aggregates`、`self_correlation`、`prod_correlation`。

仅观察登记：`operators`、`alpha_check`、`pnl`。这些接口没有被生产 client 自动调用；只有 capability probe 或脱敏 fixture 可以证明其当前可用性。

Retry-After 支持秒数和 HTTP-date，统一由 `retry_after_seconds()` 解析，并拒绝负数、非有限值和畸形值。429 仍受全局 gate 与预算约束，Simulation POST 的未知结果仍进入 `SUBMIT_UNKNOWN`。

## 脱敏 fixtures

`tests/fixtures/brain/` 只包含结构样例，不包含真实账号、alpha、token、字段目录或平台数据。fixture 验证只能产生 `FIXTURE_VERIFIED`，不能替代 live response。
