# 辅助工具

生产模拟不在本目录执行；请使用根目录的 `main.py`。这里仅保留针对当前状态或历史证据的独立工具。

| 工具 | 用途 |
|---|---|
| `check_health.py` | 查询指定 alpha 的持仓分散度与健康 checks |
| `maintain_memory.py` | 检查并维护 `.wqb_state/experience.json` |
| `archive_completed_rounds.py` | dry-run/归档已完成旧轮次摘要与 checkpoint，默认保留最近 10 个；省略 `--archive-dir` 时使用 state-dir 同级项目的 `docs/archive` |
| `generate_report.py` | 从当前状态生成研究报告 |
| `validate_integrity.py` | 校验历史研究账本完整性 |
| `validate_high_signal.py` | 为高信号结果生成有限验证计划 |
| `audit_high_signal.py` | 审计历史高信号记录 |
| `check_correlation.py` | 查询或整理相关性证据 |
| `export_platform_fields.py` | 导出字段目录 |
| `list_fields.py` | 列出字段缓存内容 |
| `query_ledger.py` | 查询历史研究账本 |
| `generate_ledger.py` | 生成历史账本摘要 |
| `curate_data.py` | 整理历史研究数据 |

旧的编号阶段管线和 `scratch/` 临时脚本已移除，避免与当前 `main.py` 两阶段生产流程混用。

```powershell
python scripts/check_health.py <alpha_id>
python scripts/maintain_memory.py
python -m unittest discover -s tests
```
