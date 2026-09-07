# 运维脚本

生产模拟不在本目录执行；请使用根目录的 `main.py` 或 `wqb_agent.research_api`。这里仅保留少量安全运维工具。

| 工具 | 用途 | 边界 |
|---|---|---|
| `reconcile_pending.py` | 只读对账 UNKNOWN/PENDING Simulation | 已知 URL 只轮询，绝不重 POST |
| `validate_integrity.py` | 审计本地证据、账本和状态一致性 | 输出是派生诊断，不替代事实源 |
| `archive_completed_rounds.py` | 归档已完成的派生 round/checkpoint | 默认 dry-run；`--apply` 前需锁、checkpoint 审计和用户确认 |
| `check_correlation.py` | 读取 BRAIN self-correlation | 只读平台检查 |
| `check_health.py` | 读取 DONE Alpha 健康指标 | 只读平台检查 |

已删除的 report、ledger、schema enhance、memory maintenance 和一次性导入脚本不再是当前工程入口；完整历史由 Git 保留，研究事实仍从 `.wqb_state` 和 BRAIN 获取。

```powershell
python scripts/reconcile_pending.py --state-dir .wqb_state
python scripts/validate_integrity.py
python scripts/archive_completed_rounds.py --state-dir .wqb_state
```
