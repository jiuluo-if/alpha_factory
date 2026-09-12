# 本地性能记录（Phase VII）

本文件记录 2026-09-12 Phase VII 建立的 offline benchmark harness、实测 baseline/after 数字、profiling 证据与依赖评估结论。
它只描述本地 JSON/JSONL 与 canonical merge 成本，不是 BRAIN/平台延迟报告：所有 workload 都在临时目录上用 synthetic 数据生成，不接触网络。

## 1. Harness

```powershell
python scripts/benchmark_local_io.py
python scripts/benchmark_local_io.py --rows 1000,10000,50000 --repeat 3
python scripts/benchmark_local_io.py --workloads trajectory_find_row_batch,research_api_compare --repeat 5
python scripts/benchmark_local_io.py --workloads jsonl_decode --codecs json,orjson
python scripts/benchmark_local_io.py --output research_data/benchmark_local_io.txt
```

- offline only；synthetic rows；临时目录；无 `Client`、无 `Simulator`、无 network、不读写 `.wqb_state`。
- 默认 stdout，只有显式 `--output` 才落盘；raw 输出属于 local artifact（`research_data/` 已被 `.gitignore` 覆盖），不提交。
- 输出列：`workload` / `rows` / `implementation` / `median_ms` / `p95_ms`；每个 workload 先跑 1 次不计入的 warmup。
- smoke test 只验证 harness 可执行：`tests/test_benchmark_harness.py`；长基准不进普通 unit test / CI lane。
- 本文数字环境：Python 3.11.9 / Windows / `--repeat 3` / synthetic 1k、10k、50k 行。

## 2. 已应用的优化（commit `5da9565`）

profile 支持的问题：

- `Trajectory.find_row()` 每次调用都流式扫描整个 append-only 文件；
- `research_api.compare_experiments()` 对每个 id 各调用一次 `find_row()` → `N × full scan`；
- `Trajectory.iter_rows()` 对每行都做 `json.loads`，即使该行不可能包含目标 identity。

修复：

- 新增 owner-local `Trajectory.find_rows(ids)`：单次 streaming canonical merge pass 解析多个 identity，保留 `find_row` 的 per-id 语义（最新合法 revision 胜出；execution identity 冲突的 revision 被忽略；缺失 identity 返回 `None`，不伪造）。
- `research_api.compare_experiments()` 复用该批量原语，不再 N 次重开文件。
- `iter_rows(prefilter=...)` 支持在 JSON 解码前跳过不可能匹配的原始行；`json_literal_prefilter()` 对含引号、反斜杠、控制字符或非 ASCII 的 identity 退回全量解码（fail-closed，不改变任何 yield 结果）。
- `find_row()` 同样使用该预筛。

语义：`semantic diff = none`；回归测试 `tests/test_trajectory_batch_reads.py`（revision merge、identity 冲突、需要转义的 identity、missing identity、batch/single-id 一致性、compare 单次读取）。

before/after（median_ms，synthetic trajectory，`--repeat 3`）：

| workload | rows | before | after | speedup |
|---|---|---|---|---|
| `research_api_compare`（16 ids） | 1000 | 155.514 | 5.170 | 30.1x |
| `research_api_compare`（16 ids） | 10000 | 1576.713 | 48.697 | 32.4x |
| `research_api_compare`（16 ids） | 50000 | 7681.628 | 241.353 | 31.8x |
| `research_api_get_experiment`（16 次单查） | 1000 | 155.749 | 38.003 | 4.1x |
| `research_api_get_experiment`（16 次单查） | 10000 | 1543.693 | 379.725 | 4.1x |
| `research_api_get_experiment`（16 次单查） | 50000 | 7817.804 | 1830.608 | 4.3x |
| `trajectory_find_row_batch`（32 ids） | 1000 | 315.095 | 75.955 | 4.1x |
| `trajectory_find_row_batch`（32 ids） | 10000 | 3103.795 | 757.471 | 4.1x |
| `trajectory_find_row_batch`（32 ids） | 50000 | 15511.904 | 3646.423 | 4.3x |

未变化的 workload（噪声范围内约 ±5%）：`trajectory_load`、`trajectory_iter_canonical`、`trajectory_iter_rows`、`artifacts_*`、`discovery_*`、`jsonl_decode`。

未证实收益的候选（不做改动）：`find_completed_expressions` 的 repeated canonicalization / 解码成本。实验中给 `canonical_expression` 加有界缓存后该 workload 在 50k 行仍为 1195 ms → 1172 ms（无实质收益），因此该改动被回退，不提交未证明的 `perf`。

## 3. Profiling 证据

```powershell
python -m cProfile -s tottime scripts/benchmark_local_io.py --rows 10000 --repeat 2 --workloads trajectory_find_row_batch,research_api_compare,trajectory_iter_rows
py-spy record -o research_data/profile_local_io.svg -- python scripts/benchmark_local_io.py --rows 10000 --repeat 3 --workloads trajectory_find_row_batch,research_api_compare,trajectory_iter_rows
```

- cProfile：`state.py:iter_rows`（tottime 3.536 s / cumtime 4.269 s）与 `json` 解码是主导成本。
- py-spy 0.4.2：422 samples、0 errors；profile 输出留在本地 `research_data/`，不提交。

## 4. 依赖评估（Phase VII budget：runtime ≤ 1、dev/perf ≤ 3）

| 候选 | 用途 | 检查版本 | Python 3.11 | Windows | License | 维护 | baseline | after | 语义风险 | 决策 |
|---|---|---|---|---|---|---|---|---|---|---|
| py-spy | dev-only CPU sampling | 0.4.2 | 支持 | 支持（wheel，binary） | MIT | 活跃 | - | 422 samples / 0 errors | 只用于 profiling，不进入 runtime | ADOPT（dev-only extra `perf`） |
| orjson | runtime JSON/JSONL decode A/B | 3.12.0 | 支持 | 支持 | MIT / Apache-2.0 | 活跃 | `jsonl_decode` 50k = 378.05 ms | orjson 137.57 ms（2.75x） | 见 §4.1 | REJECT → `NO_RUNTIME_LIBRARY_CHANGE` |
| pytest + pytest-xdist | dev-only 本地测试 lane | pytest 9.1.1 / pytest-xdist 3.8.0 | 支持 | 支持 | MIT | 活跃 | `unittest` 867/876 tests OK（CI authoritative，最终树 888） | 串行 57.05 s / xdist 44.06 s（均 888 passed，两轮一致） | 并行遇共享文件系统状态会改变行为；CI lane 不变 | ADOPT（dev-only extra `perf`） |
| msgspec | typed serialization | 未安装 | - | - | - | - | - | - | 当前 Experiment / platform evidence / legacy rows 存在大量动态兼容结构 | `DO_NOT_ADOPT_MSGSPEC` |

未引入（本轮明确不做）：pandas / polars / numpy / duckdb / aiohttp / httpx / uvloop / cachetools / diskcache；也不把 `requests` 换成异步传输（会触碰 retry、checkpoint、`SUBMIT_UNKNOWN`、reconciliation、rate limit）。

### 4.1 orjson 语义实验（offline probe：16 decode case + 6 dumps case）

- decode 16 个 case 中 10 个行为不同，其中关键：
  - `NaN` / `Infinity` / `1e400`：`json` 正常解析，`orjson` 抛 `JSONDecodeError`；
  - 大整数 `123456789012345678901234567890`：`json` 保留精确 `int`，`orjson` 变成 `float`（`1.2345678901234568e+29`，静默精度损失）；
  - BOM 前缀：两者都拒绝，但错误类型不同。
- dumps：`json` 写 `NaN` / `Infinity`，`orjson` 写成 `null`（静默语义改变）；`{1: "a"}` 在 `orjson` 默认 `TypeError`（需 `OPT_NON_STR_KEYS`）；分隔符与 `indent` 细节不同。
- 结论：即使 decode 快 2.75x，也无法满足"历史 malformed row 的 fail-closed 行为不改变"这一硬约束；兼容层成本高于收益，不引入。

## 5. Test lane（本地加速，非权威）

```powershell
python -m unittest discover -s tests
python -m pytest -q --durations=30
python -m pytest -q -n auto --dist=loadfile
```

- CI authoritative lane 仍是 `python -m unittest discover -s tests`（未替换、未并行化）。
- 慢测试（测试拆分后复测，`python -m pytest -q --durations=12`）：`tests/test_factory_batch_contract.py::TestFactoryBatchContract::test_factory_exploration_is_seeded_and_marked_as_signal_discovery` 39.53 s，其次 `tests/test_factory_provenance_persistence.py::TestFactoryProvenancePersistence::test_factory_batch_prefers_cross_dataset_companions_and_reports_stats` 5.03 s、`tests/test_control_loop_repair.py::TestHistoricalCorrelationBackfill::test_selection_reaches_beyond_the_in_memory_window` 3.69 s。
- 拆分后复测：`python -m unittest discover -s tests` = 888 tests OK / 63.2 s；`pytest -q` = 888 passed（43 subtests）/ 58.94 s；`pytest -q -n auto --dist=loadfile` = 888 passed / 44.89 s；coverage branch-aware 80.1%（未变）。

## 6. 未改变

- durability contract：未删除任何 `flush()` / `fsync()` / `os.replace()`；
- Simulation owner、checkpoint、`SUBMIT_UNKNOWN` exactly-once、trajectory schema、reward/optimizer 语义均未改动。
