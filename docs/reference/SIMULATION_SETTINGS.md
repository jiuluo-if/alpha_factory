# Simulation Settings 设置语义与调参纪律

> 来源：BRAIN 官方文档《How to choose the Simulation Settings》（用户提供原文）+ 本项目默认配置（`config.json` → `simulation`）。
> 授权范围（用户 2026-08-18 确认）：**Universe / Truncation / Decay 三个参数允许修改**；其余参数保持项目默认。改动必须遵守下方「调参纪律」。

## 0. 本项目默认设置（config.json）

```json
{"instrumentType":"EQUITY","region":"USA","universe":"TOP3000","delay":1,"decay":4,"neutralization":"SUBINDUSTRY","truncation":0.08,"pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"OFF","language":"FASTEXPR"}
```

## 1. 可调参数白名单（仅这三个）

| 参数 | 默认 | 合法值 | 官方语义 | 本项目约束 |
|------|------|--------|----------|-----------|
| **Universe** | `TOP3000` | BRAIN 提供的 universe（如 `TOP1000`/`TOP2000`/`TOP3000`，按日均美元成交额流动性排序） | 一组预制的可交易标的集合；`TOP3000` = 美股流动性前 3000 | 只改 universe 名，其余不变；改动理由须写入提案 rationale |
| **Truncation** | `0.08` | 浮点 `0 ≤ x ≤ 1`（越界破坏模拟）；`0` = 无限制 | 单只股票在组合中的最大权重；防止对单只个股过度暴露；官方推荐 `0.05–0.1`（5-10%） | 只在 `0.02–0.15` 范围内步进；`0`（无限制）禁止（等同放弃风险约束） |
| **Decay** | `4` | 整数 `n ≥ 0`（负数/非整数破坏模拟） | 对过去 n 天做线性衰减加权平均；可降换手，但过大衰减会钝化信号 | 只在整数 `0–10` 内步进；每次 ±1（单步） |

### Decay 官方公式（线性衰减加权移动平均）

```text
Decay_linear(x, n) = [x[date]*n + x[date-1]*(n-1) + ... + x[date-n+1]*1] / [n + (n-1) + ... + 1]
                  = (2 / (n*(n+1))) * sum_{i=0}^{n-1} x[date-i] * (n-i)
```

权重从 n 线性递减至 1，近期数据权重更高；分母为等差数列和 n(n+1)/2。

## 2. 不可调参数（保持默认，勿改）

- **region**: `USA`（Europe/Asia 仅对研究顾问开放）
- **delay**: `1`（决策次日交易；delay 0 为激进同日交易，本项目不采用）
- **neutralization**: `SUBINDUSTRY`（组内减组均值，多空中性）
- **pasteurization**: `ON`（非 Alpha universe 标的输入置 NaN；关闭需手动 `pasteurize(x)`）
- **nanHandling**: `OFF`（NaN 保留，需表达式内手动处理；On 会用 0 填充时序算子、用组值填充分组算子，可能引入歧义信息）
- **language**: `FASTEXPR`；**instrumentType**: `EQUITY`；**unitHandling**: `VERIFY`

## 3. 调参纪律（用户要求：约束调参，禁止无理由扫参）

### 3.1 允许调参的动机（三选一，写入提案 rationale）

1. **稳健性检验**：验证某表达式在 Universe/Decay/Truncation 变化下结论是否稳健（对应 r225 假设：CFO/EV 对设置变化的稳健性）。
2. **机制驱动**：有明确经济/统计理由——如持仓过度集中（CONCENTRATED_WEIGHT 风险）→ 降低 truncation；换手过高 → 提高 decay；信号衰减快 → 降低 decay。
3. **提交适配**：为满足评级门槛（如 Excellent 要求 TO ≤ 30%）或平台检查而调整（如用 decay 降换手）。

### 3.2 禁止行为

- ❌ 无机制理由的组合扫参（grid search 多个设置同时改）；
- ❌ 同表达式在默认设置 FAIL 后，靠改设置“救活”（违反先证伪后调参，见 research_agent.md 原则 10）；
- ❌ 一次改多个可调参数（必须单变量：每轮最多改一个参数，其余保持默认）；
- ❌ truncation 设为 `0`（无限制）或越界值；decay 用负数/非整数；
- ❌ 为调参而调参：设置变化没有对应的假设或证伪判据。

### 3.3 执行规范

- 在 `proposals.json` 的提案里显式带 `settings` 字段（框架已支持 `p.get("settings")`，且 Experiment 会把 settings 持久化进 trajectory 可追溯）；
- 调参提案必须与基线（同表达式 + 默认设置）对照，只保留显著改善且结论一致的结果；
- 每个设置组合只模拟一次（trajectory 去重覆盖表达式，settings 组合注意人工避免重复）；
- 调参结果写回记忆：哪些设置对该信号族有效/无效，避免重复探索。

## 4. 已确认的设置事实（官方）

- Delay 0 = 当日收盘前交易（激进）；Delay 1 = 次日交易（保守，本项目用）。
- Truncation 推荐 0.05–0.1；值太大等于没限制，太小持仓过于分散。
- Decay 降换手但衰减过大钝化信号；n=0 即无衰减。
- Pasteurize ON 时非 universe 标的输入为 NaN，横截面/分组算子只在 universe 内计算；OFF 时可用 `pasteurize(x)` 手动控制。
- NaNHandling ON 会增加覆盖但可能引入歧义（0 可能是“均值相等”也可能是“无数据”）；OFF 是默认，NaN 需表达式内处理（如 `is_nan(a) ? b : a`）。

---

_版本：2026-08-18（用户授权 Universe/Truncation/Decay 可调 + 官方文档整理）。_
