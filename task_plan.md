# 任务计划：运行数据审查、清理与工厂/Agent 边界修复

## 已完成目标

审查最近运行产生的数据，诊断 Agent/执行链问题；核对并删除用户指定的外部 `.wqb_state`，以及本仓库中经过证据确认的多余生成物。

## 已完成阶段

- [x] 只读接管：读取核心源码、相关测试、运行上下文和状态目录
- [x] 数据审计：按时间、checkpoint、trajectory、ledger、proposals、日志对账
- [x] 根因诊断：区分 Agent 判断问题、执行器问题、环境/数据证据问题
- [x] 清理核准：形成删除清单，确认不触碰未完成研究状态
- [x] 执行清理：删除已授权目标并记录结果
- [x] 完成验证：复查路径、状态、测试/编译和剩余风险

## 当前阶段

清理目标和新阶段实现均已完成：工厂每批固定 100 个题案，Agent 只生成有证据的优化题案，模板负责受控广度，避免参数过拟合；结果/提交/颜色数据按美国东部日只在进程内缓存，检查点保留恢复边界。

## 新阶段

- [x] 先锁定纽约本地日内存缓存和只保留 checkpoint 的失败测试
- [x] 固定工厂 100 题案 gate，拆分 Agent 优化/模板角色
- [x] 加强抗过拟合结构检查和 Alpha 颜色只读检测
- [x] 移除结果、提交池、trajectory、ledger、轮次摘要的默认落盘
- [x] 完整测试、编译、lint、代码审查和生成物复核

## 多数据集与多字段改造

- [x] 用失败测试锁定多数据集覆盖、目录固化、双字段和三字段占位符契约
- [x] 实现纽约本地日字段目录、可复现分层轮询和 `(dataset_id, field_id)` 画像身份
- [x] 接通 `{data_field}`、`{p}`、`{s}`、`{t}` 通用模板及 `field_refs`
- [x] 将数据集覆盖、模板分布和跨数据集组合纳入 100 题案 gate/统计
- [x] 真实平台只读 `--suggest` 复核最终数据集分布和目录 manifest
- [x] 完成 fresh code review、compileall、ruff、生成物与状态目录复核

## 设计与执行记录

- 设计：`docs/superpowers/specs/2026-09-08-factory-agent-boundaries-design.md`
- 计划：`docs/superpowers/plans/2026-09-08-factory-agent-boundaries.md`
- 采用整批 gate：不足 100 个唯一且预检通过的题案时，不部分提交、不填充重复题案。

## 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| Superpowers 初始路径不存在 | 1 | 已定位实际安装路径，改用 `C:\\Users\\联想\\.agents\\skills\\superpowers\\...` |

## 2026-09-09 增量修复阶段

- [x] 只读接管 round 2，等待旧进程退出并核对 `DONE/FAILED/UNKNOWN/PENDING` 与 session 账目
- [x] 修复已知 `progress_url` 的普通 `UNKNOWN` 不阻塞独立 `PENDING` 派发；保留 `SUBMIT_UNKNOWN` exactly-once 暂停
- [x] 修复新 factory session 恢复 checkpoint 时缺失 `last_round` 的账目映射
- [x] 最小回归、架构回归、全量 unittest、compileall、Ruff 与 diff check
- [ ] 等待当前 round 3 远程批次收敛后做最终状态对账与生成物复核

## 当前下一步

等待当前 `python main.py --factory-run --factory-hours 0.5` 自然返回；只读核对 round 3 checkpoint、session、锁和进程，随后清理本轮构建缓存并完成最终验证记录。
