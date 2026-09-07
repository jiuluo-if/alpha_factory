"""Periodic Memory Maintenance for the self-evolving research agent.

Mirrors the self-evolution maintenance protocol (prompts/self_evolution.md):

1. 去重     dedupe / compress similar lessons (evidence accumulates)
2. 压缩     cap lists to configured maxima
3. 验证     lessons must carry evidence from real simulations
4. 更新     confidence decays for stale lessons
5. 降权     stale low-evidence lessons get confidence cut
6. 遗忘     stale low-evidence lessons are SOFT-DELETED into the garbage
            tier (tombstones, restorable) — never hard-dropped here
7. 晋升     high-evidence lessons are surfaced as stable rules (top of list)
8. 缺口     report unresolved next ideas / failed hypotheses

Three-tier memory is maintained here:
- short_term entries older than the window expire: repeated observations
  promote to long-term lessons, the rest go to the garbage tier;
- garbage tombstones older than garbage_max_age_rounds are physically purged
  (dry-run by default, persisted only with --apply).

Default is read-only (dry-run). Use --apply to persist changes.

Usage:
    python scripts/maintain_memory.py --state-dir .wqb_state
    python scripts/maintain_memory.py --state-dir .wqb_state --apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.memory import ExperienceMemory  # noqa: E402
from wqb_agent.state import Trajectory  # noqa: E402
from wqb_agent.context import write_context  # noqa: E402
from wqb_agent.locking import acquire_os_owner_lock, release_os_owner_lock  # noqa: E402


def _short(value, limit):
    """Render optional memory text without letting malformed state abort maintenance."""
    return str(value or "")[:limit]


def refresh_context(state_dir, memory):
    """Rewrite context.md so it reflects the maintained memory (otherwise
    context.md stays stale until the next research round)."""
    traj = Trajectory(
        max_len=100,
        path=os.path.join(state_dir, "trajectory.jsonl"),
    ).load()
    write_context(state_dir, memory, traj.recent(20), context_experiments=10)


def compact_only(state_dir, apply=False):
    """Only compact the canonical memory representation; keep conclusions.

    The default remains a true preview: loading and compacting an in-memory
    view must not rewrite ``experience.json`` or ``context.md``.  This is
    important for a long-running factory because a maintenance probe should
    not itself become a state transition.
    """
    lock_path = os.path.join(state_dir, "run.lock")
    lock_handle = acquire_os_owner_lock(lock_path)
    if lock_handle is None:
        raise RuntimeError("active research owner exists; memory maintenance refused")
    try:
        memory = ExperienceMemory(state_dir).load()
        memory_path = memory.memory_path()
        before = os.path.getsize(memory_path) if os.path.exists(memory_path) else 0
        if apply:
            memory.save()
            refresh_context(state_dir, memory)
            after = os.path.getsize(memory_path)
        else:
            after = before
        return (
            f"Memory compact-only for {state_dir}: {before} -> {after} bytes; "
            f"seen_expressions={len(memory.seen_expressions)}; "
            f"{'applied' if apply else 'dry-run, not saved'}; "
            "no research verdict changed."
        )
    finally:
        release_os_owner_lock(lock_handle)


def maintain(state_dir, apply=False, staleness=10, min_evidence=2, promote_evidence=5):
    memory = ExperienceMemory(state_dir).load()
    report = []
    changed = False

    lessons = memory.lessons
    now_round = memory.updated_round

    # ---- 3. validate + 5. downgrade + 6. forget (soft) ------------------
    kept = []
    forgotten = []
    downgraded = []
    for lesson in lessons:
        evidence = lesson.get("evidence", 0)
        source = lesson.get("source_round", 0)
        stale = (now_round - source) >= staleness
        if evidence == 0 or (stale and evidence < min_evidence):
            forgotten.append(lesson)
            memory.move_to_garbage(
                "lesson", lesson, reason="stale",
                note=f"evidence={evidence} < min_evidence={min_evidence}, "
                     f"source_round={source}, now={now_round}",
                round_no=now_round,
            )
            changed = True
            continue
        if stale and evidence < promote_evidence:
            # promoted stable rules keep their confidence; only stale
            # non-promoted lessons get downgraded.
            lesson["confidence"] = round(lesson.get("confidence", 0.5) * 0.8, 3)
            downgraded.append(lesson)
            changed = True
        kept.append(lesson)
    memory.lessons = kept

    # ---- 7. promote: high-evidence lessons surface first -----------------
    promoted = [l for l in memory.lessons if l.get("evidence", 0) >= promote_evidence]
    memory.lessons.sort(key=lambda l: -l.get("evidence", 0))

    # ---- 6a. short-term expiry (promote repeated observations / trash) ---
    promoted_st, trashed_st = memory.expire_short_term(now_round=now_round)
    if promoted_st or trashed_st:
        changed = True

    # ---- 1+2. dedupe + compress (caps and similarity merge) --------------
    memory.compress()

    # ---- 1b. merge near-duplicate next ideas (keep highest priority) -----
    next_before = len(memory.next)
    merged_next = []
    for idea in sorted(memory.next, key=lambda x: -x.get("priority", 0)):
        if not any(memory._similar(idea.get("idea", ""), m.get("idea", ""), threshold=0.6) for m in merged_next):
            merged_next.append(idea)
        else:
            changed = True
    if len(merged_next) < len(memory.next):
        memory.next = merged_next
        report.append(f"  next merged: {next_before} -> {len(memory.next)} (similar ideas)")

    # ---- 1c. merge near-duplicate avoid directions (keep latest reason) --
    avoid_before = len(memory.avoid)
    merged_avoid = []
    for item in sorted(memory.avoid, key=lambda x: -x.get("updated", 0)):
        if not any(memory._similar(item.get("direction", ""), m.get("direction", ""), threshold=0.6) for m in merged_avoid):
            merged_avoid.append(item)
        else:
            changed = True
    if len(merged_avoid) < len(memory.avoid):
        memory.avoid = merged_avoid
        report.append(f"  avoid merged: {avoid_before} -> {len(memory.avoid)} (similar directions)")

    # ---- 6b. forget stale low-relevance avoid entries (soft) -------------
    stale_avoid = [
        a for a in memory.avoid
        if (now_round - a.get("source_round", 0)) >= staleness * 2
        and (a.get("reason") or "").count("Sharpe") == 0  # 保留含具体指标的原因
    ]
    if stale_avoid:
        # 用对象身份剔除，避免 == 语义误删内容恰好相同的另一条记录。
        stale_ids = {id(a) for a in stale_avoid}
        memory.avoid = [a for a in memory.avoid if id(a) not in stale_ids]
        for item in stale_avoid:
            memory.move_to_garbage(
                "avoid", item, reason="stale",
                note="generic reason without metrics, stale for 2x window",
                round_no=now_round,
            )
        report.append(f"  avoid forgotten: {len(stale_avoid)} (stale, generic reasons, -> garbage)")
        changed = True

    # ---- 6c. purge old tombstones (physical delete, dry-run first) -------
    purge_candidates = memory.purge_garbage(now_round=now_round, dry_run=True)
    if purge_candidates:
        if apply:
            memory.purge_garbage(now_round=now_round, dry_run=False)
        report.append(
            f"  garbage purge candidates: {len(purge_candidates)} "
            f"(age > {memory.garbage_max_age_rounds} rounds)"
        )

    # ---- 8. discover gaps ------------------------------------------------
    gaps = []
    open_next = memory.top_next(5)
    if not open_next:
        gaps.append("no open next experiments")
    for hyp in memory.active_hypotheses:
        if hyp.get("status") == "failed":
            gaps.append(f"failed hypothesis: {hyp.get('id')} ({_short(hyp.get('statement'), 60)})")
    low_priority = [x for x in memory.next if x.get("priority", 0) <= 2]
    if low_priority:
        gaps.append(f"{len(low_priority)} low-priority next ideas may be stale")

    # ---- report -----------------------------------------------------------
    gstats = memory.garbage_stats()
    report.append(f"Memory maintenance for {state_dir} (updated_round={now_round})")
    report.append(f"  lessons      : {len(lessons)} -> {len(memory.lessons)}"
                  f"  (forgotten->garbage={len(forgotten)}, downgraded={len(downgraded)}, promoted={len(promoted)})")
    report.append(f"  avoid        : {len(memory.avoid)}")
    report.append(f"  next         : {len(memory.next)}")
    report.append(f"  hypotheses   : {len(memory.active_hypotheses)}")
    report.append(f"  seen_expressions: {len(memory.seen_expressions)}")
    report.append(f"  short_term   : {len(memory.short_term)}"
                  f"  (promoted={len(promoted_st)}, trashed->garbage={len(trashed_st)})")
    report.append(f"  garbage      : {gstats['total']}"
                  f"  (by_reason={gstats['by_reason']})")
    if forgotten:
        report.append("  forgotten (soft, restorable via garbage):")
        for item in forgotten:
            report.append(f"    - [{item.get('id')}] {_short(item.get('claim'), 80)}")
    if downgraded:
        report.append("  downgraded (confidence x0.8):")
        for item in downgraded[:5]:
            report.append(f"    - [{item.get('id')}] {_short(item.get('claim'), 80)}")
    if promoted:
        report.append("  promoted (stable rules):")
        for item in promoted:
            report.append(f"    - [ev={item.get('evidence')}] {_short(item.get('claim'), 80)}")
    if promoted_st:
        report.append("  short-term promoted to lessons:")
        for item in promoted_st:
            report.append(f"    - [ev={item.get('evidence')}] {_short(item.get('claim'), 80)}")
    if trashed_st:
        report.append("  short-term trashed (-> garbage):")
        for item in trashed_st[:5]:
            report.append(f"    - [{item.get('kind')}] {_short(item.get('text'), 80)}")
    if purge_candidates:
        report.append("  garbage purge candidates (dry-run; --apply deletes):")
        for item in purge_candidates[:5]:
            report.append(
                f"    - [{item.get('id')}] kind={item.get('kind')} "
                f"reason={item.get('reason')} moved_round={item.get('moved_round')}"
            )
        if not apply:
            report.append("    ... run with --apply to physically delete them.")
    if gaps:
        report.append("  gaps:")
        for gap in gaps:
            report.append(f"    - {gap}")
    else:
        report.append("  gaps: none")

    if apply:
        memory.save()
        refresh_context(state_dir, memory)
        if changed:
            report.append("  [applied] memory saved, context.md refreshed.")
        else:
            report.append("  [applied] no memory change; context.md refreshed.")
    elif changed:
        report.append("  [dry-run] changes NOT saved; re-run with --apply to persist.")
    else:
        report.append("  [clean] nothing to change.")

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", default=".wqb_state")
    parser.add_argument("--apply", action="store_true",
                        help="persist maintenance changes (default: dry-run)")
    parser.add_argument(
        "--compact-only", action="store_true",
        help="仅压缩 experience.json 并刷新 context.md，不做遗忘/降权/清理",
    )
    parser.add_argument("--staleness", type=int, default=10,
                        help="rounds after which a lesson counts as stale")
    parser.add_argument("--min-evidence", type=int, default=2,
                        help="minimum evidence to keep a stale lesson")
    parser.add_argument("--promote-evidence", type=int, default=5,
                        help="evidence threshold for promotion to stable rule")
    args = parser.parse_args()

    if args.compact_only:
        print(compact_only(args.state_dir, apply=args.apply))
        return 0

    print(maintain(
        args.state_dir,
        apply=args.apply,
        staleness=args.staleness,
        min_evidence=args.min_evidence,
        promote_evidence=args.promote_evidence,
    ))


if __name__ == "__main__":
    main()
