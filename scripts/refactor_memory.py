"""按证据导入研究账本中的少量关键经验。

这是旧账本导入器的安全重写：默认只预览，不直接改写压缩记忆，也不再
生成一次性 ``memory_refactor_summary.json``。只有 ``--apply`` 才会通过
``ExperienceMemory`` 的 API 写入一条去重后的 lesson/avoid。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.context import write_context  # noqa: E402
from wqb_agent.artifacts import iter_jsonl_objects  # noqa: E402
from wqb_agent.locking import acquire_os_owner_lock, release_os_owner_lock  # noqa: E402
from wqb_agent.memory import ExperienceMemory  # noqa: E402
from wqb_agent.state import Trajectory  # noqa: E402


def build_evidence(data_dir):
    sims_path = os.path.join(data_dir, "simulations_final.jsonl")
    total = done = noise = source_round = 0
    for row in iter_jsonl_objects(sims_path):
        total += 1
        if row.get("status") == "DONE":
            done += 1
        round_value = row.get("round")
        if str(round_value or "").isdigit():
            source_round = max(source_round, int(round_value))
        if str(
            row.get("heuristic_validation_status")
            or row.get("heuristic_status")
            or ""
        ).upper() in {"NOISE_TRAP", "SUSPICIOUS"}:
            noise += 1
    return {
        "total": total,
        "done": done,
        "noise": noise,
        "source_round": source_round,
    }


def _has_similar(memory, claim):
    return any(
        memory._similar(item.get("claim", ""), claim, threshold=0.8)
        for item in memory.lessons
    )


def run(state_dir, data_dir, apply=False):
    evidence = build_evidence(data_dir)
    memory = ExperienceMemory(state_dir).load()
    source_round = evidence["source_round"] or memory.updated_round
    claim = (
        f"研究账本 {os.path.abspath(data_dir)} 记录 {evidence['total']} 次 Simulation，"
        f"其中 DONE={evidence['done']}、启发式噪声/可疑标记={evidence['noise']}；"
        "后续判断必须回溯原始 simulation 证据。"
    )
    actions = []
    if not _has_similar(memory, claim):
        actions.append("add one evidence-backed ledger lesson")
        if apply:
            memory.add_lesson(claim, source_round, evidence=1, confidence=0.5)
    # Heuristic labels are derived review hints, not research evidence.  Do
    # not turn them into durable ``avoid`` memory; real robustness results
    # must return through the production reflection path first.
    if apply and actions:
        memory.updated_round = max(memory.updated_round, source_round)
        memory.save()
        trajectory = Trajectory(
            max_len=100, path=os.path.join(state_dir, "trajectory.jsonl")
        ).load()
        write_context(state_dir, memory, trajectory.recent(20), context_experiments=10)
    mode = "applied" if apply else "dry-run"
    return (
        f"[{mode}] ledger total={evidence['total']} DONE={evidence['done']} "
        f"noise={evidence['noise']}; actions={actions or ['none']}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", default=".wqb_state")
    parser.add_argument("--data-dir", default="research_data")
    parser.add_argument("--apply", action="store_true", help="通过 ExperienceMemory API 写入")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.data_dir):
        parser.error(f"data directory not found: {args.data_dir}")
    if not args.apply:
        print(run(args.state_dir, args.data_dir, apply=False))
        return 0
    lock_path = os.path.join(args.state_dir, "run.lock")
    lock_handle = acquire_os_owner_lock(lock_path)
    if lock_handle is None:
        raise SystemExit("active research owner exists; memory import refused")
    try:
        print(run(args.state_dir, args.data_dir, apply=True))
    finally:
        release_os_owner_lock(lock_handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
