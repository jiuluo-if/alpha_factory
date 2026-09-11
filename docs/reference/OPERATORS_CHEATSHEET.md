# WQB Alpha 算子速查库（Operator Cheatsheet）

> 来源：BRAIN 算子文档整理（用户提供）。适用语言：FASTEXPR。
> 用法：写 Alpha 表达式前查本节；「使用状态」列标注本项目 **3042 次真实模拟（截至 r339，2026-08-19 重新统计）** 中该算子的函数调用次数（0 = 从未使用，可探索）。
> 统计口径：历史一次性统计脚本对 `trajectory.jsonl` 表达式做词边界函数调用计数（`name(` 形式；`+ - * /` 符号形式无法可靠区分，不计入）。一次性脚本归档在 `docs/archive/scratch/YYYYMMDD/`，不作为生产入口。

## 记忆核心（先记这个）

- `ts_*` = 同一标的沿时间看（回看 d 天）
- `rank / zscore / normalize` = 同一天不同标的之间看（横截面）
- `group_*` = 只在同一行业/组内比较
- `vec_*` = 将 VECTOR 信号聚合/转换为 MATRIX 信号（输入必须是 VECTOR）

---

## 1. Base：基础数学算子

| 算子 | 含义 | 关键说明 | 使用状态 |
|---|---|---|---|
| `abs(x)` | 绝对值 `\|x\|` | 去掉负号 | 0 |
| `add(x,y,filter=false)` / `x+y` | 加法 | `filter=true` 时 NaN→0 | 0 |
| `subtract(x,y,filter=false)` / `x-y` | 减法 | `filter=true` 时 NaN→0 | 0 |
| `multiply(x,y,...,filter=false)` / `x*y` | 乘法 | 支持多输入；`filter=true` 时 NaN→0 | 0 |
| `divide(x,y)` / `x/y` | 除法 | `y=0` 报错，分母可加小量 | 0 |
| `inverse(x)` | 倒数 `1/x` | `x=0` 报错 | 0 |
| `log(x)` | 自然对数 `ln(x)` | 通常要求 `x>0` | 1 |
| `max(x,y,...)` | 最大值 | 至少两个输入 | 0 |
| `min(x,y,...)` | 最小值 | 至少两个输入 | 0 |
| `power(x,y)` | `x^y` | 非整数幂可能丢负号 | 0 |
| `signed_power(x,y)` | 保留符号的幂运算 | 适合负数输入 | 1 |
| `sqrt(x)` | 非负平方根 | 等价 `power(x,0.5)`；负数无定义 | 0 |
| `reverse(x)` | 取反 | 即 `-x` | 0 |
| `sign(x)` | 符号函数 | 正→1，负→-1，0→0，NaN→NaN | 0 |
| `densify(x)` | 压缩分组编号 | 稀疏 bucket/group 映射为连续组 | 0 |

注意：`divide` / `inverse` 需防除零；`power` / `sqrt` 遇负值如需保留符号改用 `signed_power`。

## 2. Logical：逻辑/条件算子

| 算子 | 含义 | 返回值 | 使用状态 |
|---|---|---|---|
| `and(a,b)` | 且 | 两者为 1 → 1，否则 0 | 0 |
| `or(a,b)` | 或 | 至少一个 1 → 1 | 0 |
| `not(x)` | 非 | 1→0，0→1 | 0 |
| `if_else(cond,a,b)` | 条件选择 | 真→`a`，假→`b` | 2 |
| `a < b` / `<=` / `==` / `>` / `>=` / `!=` | 比较 | 真→1，假→0 | 0 |
| `is_nan(x)` | 是否缺失 | NaN→1，否则 0 | 0 |

典型：`if_else(x>0, x, 0)`。

## 3. Time Series：时间序列算子（d = 回看天数/窗口）

### 基础/缺失处理

| 算子 | 核心作用 | 直观理解 | 使用状态 |
|---|---|---|---|
| `days_from_last_change(x)` | 距上次变化天数 | “这个值多久没变了？” | 1 |
| `hump(x,hump=0.01)` | 限制输入变化幅度 | 平滑信号、降低换手 | 1 |
| `kth_element(x,d,k,ignore="NaN")` | 回看 d 天第 k 个值 | 缺失值回填 | 0 |
| `last_diff_value(x,d)` | 最近一次不同于当前值的历史值 | 找最近变化前的值 | 1 |
| `ts_delay(x,d)` | `d` 天前的值 | `x[t-d]` | 4 |
| `ts_delta(x,d)` | 当前减 `d` 天前 | `x - ts_delay(x,d)` | 289 |
| `ts_mean(x,d)` | 最近 d 天均值 | 移动平均 | 3619 |
| `ts_sum(x,d)` | 最近 d 天求和 | 滚动总和 | 181 |
| `ts_product(x,d)` | 最近 d 天连乘 | 复合增长等 | 2 |
| `ts_std_dev(x,d)` | 最近 d 天标准差 | 时序波动率 | 1 |
| `ts_count_nans(x,d)` | 最近 d 天 NaN 数 | 缺失程度 | 0 |
| `ts_backfill(x,lookback=d,k=1)` | 历史有效值填 NaN | 数据补全 | 0 |

### 极值与位置

| 算子 | 含义 | 使用状态 |
|---|---|---|
| `ts_arg_max(x,d)` | 最近 d 天最大值距今天数 | 2 |
| `ts_arg_min(x,d)` | 最近 d 天最小值距今天数 | 1 |
| `ts_av_diff(x,d)` | 当前值 − 最近 d 天均值 | **1548** |

最大值就是今天 → `ts_arg_max(...)=0`；昨天最大 → 1。
`ts_av_diff` 是 r229-239 收益率动量构造的主力算子（`ts_av_diff(OI/equity,84)` 甜点），注意它已被充分探索，新方向要给出增量机制而不是继续堆窗口。

### 相关性/回归

| 算子 | 含义 | 常见用途 | 使用状态 |
|---|---|---|---|
| `ts_corr(x,y,d)` | 最近 d 天 Pearson 相关系数 | 两变量是否同步 | 4 |
| `ts_covariance(y,x,d)` | 最近 d 天协方差 | 共同变化 | 3 |
| `ts_regression(y,x,d,lag=0,rettype=0)` | 滚动回归 | Beta、残差等 | 1 |

### 标准化/排名

| 算子 | 含义 | 输出特点 | 使用状态 |
|---|---|---|---|
| `ts_rank(x,d,constant=0)` | 当前值在自身 d 天中的排名 | 时序相对位置 | 214 |
| `ts_scale(x,d,constant=0)` | 按历史 min/max 缩放 | 约 `[0,1]` | 4 |
| `ts_zscore(x,d)` | 相对自身历史 Z-score | 距历史均值多少个标准差 | 4321 |
| `ts_quantile(x,d,driver="gaussian")` | `ts_rank` 后分布映射 | 排名转指定概率分布 | 1 |

### 平滑

| 算子 | 含义 | 使用状态 |
|---|---|---|
| `ts_decay_linear(x,d,dense=false)` | 近期高权重、历史递减 | 993 |
| `hump(x,hump=0.01)` | 限制每天信号变化幅度 | 1 |

> **2026-09-11 平台实测（round_4）**：`hump(x, 0.01)` 双参形式被拒（`exactly 1 input`），与多参 `normalize`/`winsorize` 同类；此 region 下 `hump` 仅单参 `hump(x)` 合法。
| `ts_step(1)` | 每天递增 1 的计数器 | 0 |

`ts_decay_linear` = 加权平滑；`hump` = 直接限制变化/换手。

## 4. Cross Sectional：横截面算子（同一天不同股票间）

| 算子 | 核心作用 | 典型用途 | 使用状态 |
|---|---|---|---|
| `rank(x,rate=2)` | 当日横截面排名 | 输出约 `[0,1]`，降低极端值 | 6580 |
| `zscore(x)` | 横截面 Z-score | 相对市场平均的位置 | 349 |
| `normalize(x,useStd=false,limit=0)` | 去横截面均值，可选除标准差 | 去市场整体水平 | 1 |
| `quantile(x,driver=gaussian,sigma=1)` | 排名后映射指定分布 | Gaussian/Cauchy/Uniform | 0 |
| `winsorize(x,std=4)` | 截断极端值 | 降低异常值影响 | 1 |

> **2026-09-11 平台实测（round_4）**：`winsorize(x, 4)` 双参形式被拒（`Invalid number of inputs : 2, should be exactly 1 input(s)`），与多参 `normalize` 同类；此 region 下 `winsorize` 仅单参形式 `winsorize(x)` 合法。上表参数列为文档态签名，live 以 1 参为准。
| `scale(x,scale=1,longscale=1,shortscale=1)` | 调整整体持仓规模 | 控制 book size、多空规模 | 0 |

易混淆点：

- `rank(x)`：今天不同股票之间排名
- `ts_rank(x,d)`：同一股票今天相对自己历史排名
- `zscore(x)`：今天相对其他股票
- `ts_zscore(x,d)`：今天相对自己过去 d 天

## 5. Vector → Matrix 算子

| 算子 | 含义 | 使用状态 |
|---|---|---|
| `vec_avg(x)` | 对 VECTOR 输入按内部元素取平均，输出 MATRIX | 274 |
| `vec_sum(x)` | 对 VECTOR 输入按内部元素求和，输出 MATRIX | 4 |

输入必须是平台字段类型 `VECTOR`；不得把 `vec_avg/vec_sum` 套在已标记为 `MATRIX` 的字段上。r342 的 Vector 输入是语义有效实验；r343 将 vec_* 套在 MATRIX 字段上，平台以 `status=FAIL` 终止，不能作为绩效证据。
> **2026-08-20 类型门控**：`run-proposals` 会从 suggestions/fields_cache 读取真实字段类型；vec_* 输入类型未知或不为 VECTOR 时在 Simulation 前拒绝。

## 6. Transformational：转换/交易控制算子

| 算子 | 核心作用 | 关键点 | 使用状态 |
|---|---|---|---|
| `bucket(...)` | 连续数据离散成分组 | 常与 group 系列配合 | 1 |
| `trade_when(x,y,z)` | 控制何时更新/持有/退出 Alpha | 降换手、控触发 | 0 |

`bucket` 常见写法：`bucket(rank(x), range="0,1,0.1")` → 横截面排名划 10 档，可接 `group_rank` / `group_neutralize`。

`trade_when(x,y,z)`：`x` 满足 → 更新为新 Alpha `y`；否则保留旧 Alpha；`z` 满足 → 平仓/输出 NaN。用途：控制交易时点、减少无意义换手。

## 7. Group：分组算子（行业/板块/国家/自定义组内）

| 算子 | 核心作用 | 典型用途 | 使用状态 |
|---|---|---|---|
| `group_neutralize(x,group)` | 组内减组均值 | 行业/板块中性化 | 61 |
| `group_rank(x,group)` | 组内排名 `[0,1]` | 行业内选股 | 1 |
| `group_zscore(x,group)` | 组内 Z-score | 行业内部异常程度 | 1 |
| `group_scale(x,group)` | 组内归一化 0～1 | 跨组可比 | 0 |
| `group_backfill(x,group,d,std=4)` | 同组数据填补缺失 | 数据清洗/覆盖率 | 0 |
| `group_mean(x,weight,group)` | 组内均值（harmonic） | 组内均值 | 0 |

`group_neutralize` = 从 Alpha 减去所属组平均 Alpha，消除行业/板块/国家共同暴露。

## 平台实测拒绝记录（2026-09-11，USA/EQUITY/TOP3000/Delay1）

BRAIN live response 高于本表；以下用法在本项目 300 次真实 Simulation 中被平台确定性拒绝
（rounds 1-2 FAILED 全部 42 项与 round 3 前 17 项均可归因于此 4 个算子用法）：

| 被拒用法 | 平台错误 | 现状与替代 |
|---|---|---|
| `normalize(x, true, 0.0)`（三参 form） | `Invalid number of inputs : 2, should be exactly 1 input(s)` | live `normalize` 在此 region 仅接受 1 个输入；模板已改 `rank(winsorize({p}, 4))` |
| `quantile(rank(X), gaussian, 1.0)`（裸位置参数 `gaussian`） | `Attempted to use unknown variable "gaussian"` | 裸 `gaussian` 被解析为变量；模板已改 `rank(ts_zscore(ts_delta({p}, 5), 60))`（surprise 机制等价） |
| `ts_quantile(ts_zscore(X, 20), 60, gaussian)`（裸位置参数 `gaussian`） | `Attempted to use unknown variable "gaussian"` | 模板已改 `rank(ts_rank(ts_zscore({p}, 20), 60))`（历史分位等价） |
| `group_rank(rank(group_backfill(X, g, 20, 4)), g)` | `Invalid number of inputs : 3, should be exactly 2 input(s)` | 嵌套 arity 与 live 不符；模板已改 3 参形式 `rank(subtract(ts_backfill({p}, 20), group_mean(ts_backfill({p}, 20), 1, {g})))` |
| `winsorize(X, 4)`（双参形式，round_4 实测） | `Invalid number of inputs : 2, should be exactly 1 input(s)` | 与多参 `normalize` 同类；模板已改单参 `rank(winsorize(ts_delta({p}, 5)))` |
| `hump(X, 0.01)`（双参形式，round_4 实测） | `Invalid number of inputs : 2, should be exactly 1 input(s)` | 模板已改单参 `hump(rank(ts_delta({p}, 5)))`（默认 hump 宽度） |
| `ts_regression(ts_delta(X,5), ts_step(1), 20, 0)`（lookback=0，round_4 实测） | `Got invalid value "0" for attribute "lookback"` | 模板已改省略 lookback 的 3 参形式 `ts_regression(ts_delta({p}, 5), ts_step(1), 20)` |
| `group_mean(X, G)`（2 参形式，round_9 实测） | `Invalid number of inputs : 2, should be exactly 3 input(s)` | live 形式为 3 参 `group_mean(X, 1, G)`（本表 L158：x,weight,group；r1-r7 group_scaled_mean 共 38 次 DONE）；group_filled_rank 模板已按 3 参对齐 |

已实证可用（156 条 DONE 表达式统计）：`rank` / `ts_zscore` / `ts_delta` / `ts_rank` /
`ts_std_dev` / `ts_sum` / `ts_scale` / `ts_product` / `ts_delay` / `ts_mean` / `group_mean`（仅 3 参 `group_mean(X, 1, G)`）/
`group_scale` / `ts_corr` / `ts_covariance` / `subtract` / `divide` / `ts_arg_max` / `ts_arg_min` /
`ts_decay_linear` / `trade_when` / `vec_sum` / `vec_avg` / `ts_backfill` / `reverse` / `add` /
`winsorize`（单参）/ `hump`（单参）/ `ts_regression`（省略 lookback）。
新模板默认只用已实证算子；`gaussian` 驱动、多参 `normalize` 与 `group_rank/group_backfill`
嵌套在恢复前需要平台级再验证，不作为默认模板输入。

---

## 功能 → 算子速查

| 你想做什么 | 优先考虑 |
|---|---|
| 看过去 N 天涨了多少 | `ts_delta(x,N)` |
| 获取 N 天前的数据 | `ts_delay(x,N)` |
| 算移动平均 | `ts_mean(x,N)` |
| 算历史波动率 | `ts_std_dev(x,N)` |
| 当前值相对历史是否极端 | `ts_zscore(x,N)` |
| 当前值在自身历史中的位置 | `ts_rank(x,N)` |
| 找最近 N 天最高点出现多久了 | `ts_arg_max(x,N)` |
| 找最近 N 天最低点出现多久了 | `ts_arg_min(x,N)` |
| 两变量近期是否同步 | `ts_corr(x,y,N)` |
| 横截面比较所有股票 | `rank(x)` |
| 横截面异常程度 | `zscore(x)` |
| 去极端值 | `winsorize(x)` |
| 行业内比较股票 | `group_rank(x,industry)` |
| 去除行业暴露 | `group_neutralize(x,industry)` |
| 填补缺失数据 | `ts_backfill` / `group_backfill` |
| 把股票分成十分位组 | `bucket(rank(x),range="0,1,0.1")` |
| 降低 Alpha 换手 | `hump(...)` / `trade_when(...)` |
| 保留负数符号做幂变换 | `signed_power(x,y)` |

## 未使用算子盘点（截至 r339，可探索方向）

共 **27 个**从未在项目中使用：`abs` / `add` / `subtract` / `multiply` / `divide` / `inverse` / `max` / `min` / `power` / `sqrt` / `reverse` / `sign` / `densify` / `and` / `or` / `not` / `is_nan` / `kth_element` / `ts_count_nans` / `ts_backfill` / `ts_step` / `quantile` / `scale` / `trade_when` / `group_scale` / `group_backfill` / `group_mean`。

> 注：使用状态按 `trajectory.jsonl`（3042 条，r339）统计；新表达式必须先用平台语法验证（FASTEXPR）。与 r227 相比新增使用的算子：`log` / `if_else` / `days_from_last_change` / `last_diff_value` / `ts_av_diff`(1548) / `ts_covariance` / `ts_scale` / `ts_product` / `ts_arg_min` / `ts_quantile` / `normalize` / `group_zscore` / `vec_sum`。未使用盘点从 38 降至 27。
