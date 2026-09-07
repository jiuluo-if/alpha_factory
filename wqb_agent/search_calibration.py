"""Read-only efficiency metrics and no-look-ahead policy replay."""

from collections import Counter, defaultdict
import math


def _get(row, key, default=None):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def _finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _outcome_dict(outcome):
    if isinstance(outcome, dict):
        return outcome
    if hasattr(outcome, "as_dict"):
        return outcome.as_dict()
    return {}


def build_search_calibration(ledger_summary=None, *, outcomes=(), events=(), trajectory=()):
    """Build a compact, historical efficiency report without writing state."""
    summary = ledger_summary if isinstance(ledger_summary, dict) else {}
    outcome_rows = [_outcome_dict(item) for item in outcomes]
    evaluated = [row for row in outcome_rows if row.get("evaluated") is True]
    promising = [row for row in outcome_rows if str(row.get("base_quality", "")).upper()
                 in {"PROMISING", "SUCCESS", "SUSPICIOUS_HIGH_SIGNAL", "STABLE"}]
    stable = [row for row in outcome_rows if str(row.get("robustness", "")).upper()
              in {"STABLE", "PASS"}]
    incremental_pass = [row for row in outcome_rows if str(row.get("incremental_decision", "")).upper() == "PASS"]
    portfolio = [row for row in outcome_rows if str(row.get("research_classification", "")).upper() == "PORTFOLIO_CANDIDATE"]
    cluster_sizes = [int(row.get("cluster_size")) for row in outcome_rows
                     if isinstance(row.get("cluster_size"), (int, float)) and row.get("cluster_size") > 0]
    committed = int(summary.get("committed_simulations", summary.get("submitted_count", 0)) or 0)
    if not committed:
        committed = sum(1 for row in outcome_rows if row.get("proposal_id"))
    submitted = int(summary.get("submitted_count", 0) or 0)
    if not submitted:
        submitted = committed
    role_budget = Counter()
    for row in outcome_rows:
        role = str(row.get("research_role") or "UNKNOWN")
        role_budget[role] += 1

    rejection = Counter()
    for row in events or ():
        if str(_get(row, "phase", "")) == "candidate_rejected":
            rejection[str(_get(row, "reason_code", "UNKNOWN"))] += 1
    duplicate = rejection.get("DUPLICATE_LOCAL", 0) + rejection.get("DIVERSITY_REDUNDANT", 0)
    local = rejection.get("BATCH_CAP", 0) + rejection.get("ARM_ADMISSION", 0)
    infra = sum(1 for row in outcome_rows if row.get("infrastructure_failure") is True)
    unknown = sum(1 for row in outcome_rows if str(row.get("base_quality", "")).upper() == "UNRESOLVED")

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    result = {
        "candidate_count": int(summary.get("candidate_count", summary.get("candidate_generated_count", 0)) or 0),
        "submitted_count": submitted,
        "evaluated_count": len(evaluated),
        "promising_count": len(promising),
        "stable_count": len(stable),
        "simulation_per_promising": ratio(committed, len(promising)),
        "simulation_per_stable": ratio(committed, len(stable)),
        "arm_evaluations": dict(Counter(str(row.get("arm") or "unknown") for row in evaluated)),
        "arm_mean_reward": _arm_mean(evaluated),
        "arm_success_rate": _arm_success(evaluated),
        "explore_budget": role_budget.get("EXPLORE", 0),
        "exploit_budget": role_budget.get("EXPLOIT", 0),
        "validation_budget": role_budget.get("VALIDATION", 0),
        "infra_failure_rate": ratio(infra, submitted),
        "unknown_rate": ratio(unknown, submitted),
        "duplicate_rejection_rate": ratio(duplicate, summary.get("candidate_count", 0) or 0),
        "local_rejection_rate": ratio(local, summary.get("candidate_count", 0) or 0),
        "promising_over_evaluated": ratio(len(promising), len(evaluated)),
        "stable_over_evaluated": ratio(len(stable), len(evaluated)),
        "stable_over_committed": ratio(len(stable), committed),
        "incremental_pass_count": len(incremental_pass),
        "portfolio_candidate_count": len(portfolio),
        "stable_to_incremental_rate": ratio(len(incremental_pass), len(stable)),
        "incremental_pass_per_simulation": ratio(len(incremental_pass), committed),
        "portfolio_candidate_per_simulation": ratio(len(portfolio), committed),
        "redundancy_rate": ratio(sum(1 for row in outcome_rows
                                      if str(row.get("incremental_decision", "")).upper() == "FAIL"),
                                  len([row for row in outcome_rows if row.get("incremental_decision") is not None])),
        "unique_structures_over_committed": ratio(
            len({row.get("structural_fingerprint") for row in events
                 if _get(row, "structural_fingerprint")}), committed
        ),
        "infra_failures_over_submitted": ratio(infra, submitted),
        "unknown_over_submitted": ratio(unknown, submitted),
        "simulations_to_first_promising": next(
            (index for index, row in enumerate(outcome_rows, 1)
             if str(row.get("base_quality", "")).upper()
             in {"PROMISING", "SUCCESS", "SUSPICIOUS_HIGH_SIGNAL", "STABLE"}),
            None,
        ),
        "simulations_to_first_stable": next(
            (index for index, row in enumerate(outcome_rows, 1)
             if str(row.get("robustness", "")).upper() in {"STABLE", "PASS"}),
            None,
        ),
        "role_budget": dict(role_budget),
    }
    cluster_ids = {row.get("cluster_id") for row in outcome_rows if row.get("cluster_id")}
    if cluster_ids:
        result["behavior_cluster_count"] = len(cluster_ids)
        result["mean_cluster_size"] = (
            sum(cluster_sizes) / len(cluster_sizes) if cluster_sizes else None
        )
    return result


def reward_v2(*, reward, incremental_decision=None):
    """Offline-only stage adjustment; production SearchPolicy never calls it."""
    value = _finite(reward)
    if value is None:
        return None
    decision = str(incremental_decision or "").upper()
    if decision == "PASS":
        value += (1.0 - value) * 0.25
    elif decision == "INCONCLUSIVE":
        value += (1.0 - value) * 0.05
    return max(0.0, min(1.0, value))


def _arm_mean(rows):
    values = defaultdict(list)
    for row in rows:
        reward = _finite(row.get("reward"))
        if reward is not None:
            values[str(row.get("arm") or "unknown")].append(reward)
    return {key: sum(items) / len(items) for key, items in values.items() if items}


def _arm_success(rows):
    totals, successes = Counter(), Counter()
    for row in rows:
        arm = str(row.get("arm") or "unknown")
        totals[arm] += 1
        if _finite(row.get("reward")) is not None and float(row.get("reward")) > 0:
            successes[arm] += 1
    return {arm: successes[arm] / count for arm, count in totals.items()}


class SearchPolicyReplay:
    """Replay historical candidate order using evidence available at each step."""

    def __init__(self, candidates, pool=()):
        self.candidates = [dict(row) for row in candidates or ()]
        self.pool = [dict(row) for row in pool or () if isinstance(row, dict)]

    @staticmethod
    def _time(row, position):
        for key in ("candidate_available_at", "generated_at", "sequence", "round"):
            value = _finite(row.get(key))
            if value is not None:
                return value
        return float(position)

    @staticmethod
    def _observed_at(row, position):
        for key in ("outcome_observed_at", "settled_at"):
            value = _finite(row.get(key))
            if value is not None:
                return value
        return float(position)

    @staticmethod
    def _score(row, observed, family_counts, exploration, family_penalty):
        arm = str(row.get("arm") or "unknown")
        arm_rows = observed.get(arm, [])
        count = len(arm_rows)
        mean = sum(arm_rows) / count if count else 0.0
        total = sum(len(items) for items in observed.values())
        ucb = (exploration if not count else
               mean + exploration * math.sqrt(math.log(max(2, total + 1)) / count))
        novelty = _finite(row.get("novelty")) or 0.0
        family = str(row.get("family") or arm)
        return ucb + novelty - family_penalty * family_counts[family]

    def run(self, *, strategy="current", exploration=1.0, family_penalty=0.05,
            checkpoints=(10, 25, 50, 100)):
        indexed = [(index, row, self._time(row, index + 1))
                   for index, row in enumerate(self.candidates)]
        for _, row, decision_time in indexed:
            observed_at = self._observed_at(row, 0)
            explicit_decision = _finite(row.get("decision_timestamp"))
            if explicit_decision is not None and observed_at > explicit_decision:
                raise ValueError("evidence_timestamp exceeds decision_timestamp")
            entered = _finite(row.get("pool_entered_at"))
            if explicit_decision is not None and entered is not None and entered > explicit_decision:
                raise ValueError("pool evidence is from the future")
        remaining = list(indexed)
        observed = defaultdict(list)
        family_counts = Counter()
        observed_ids = set()
        selected = []
        result = []
        observed_snapshots = {}
        pool_snapshots = {}
        step = 0
        while remaining:
            decision_time = min(item[2] for item in remaining)
            for index, row, available_at in selected:
                if index in observed_ids:
                    continue
                if self._observed_at(row, index + 1) <= decision_time:
                    reward = _finite(row.get("reward"))
                    if reward is not None:
                        observed[str(row.get("arm") or "unknown")].append(reward)
                    observed_ids.add(index)
            visible = [item for item in remaining if item[2] <= decision_time]
            if not visible:
                decision_time = min(item[2] for item in remaining)
                visible = [item for item in remaining if item[2] <= decision_time]
            if strategy == "fifo":
                chosen = min(visible, key=lambda item: item[0])
            else:
                chosen = max(
                    visible,
                    key=lambda item: self._score(item[1], observed, family_counts,
                                                 exploration, family_penalty),
                )
            remaining.remove(chosen)
            position, row, available_at = chosen
            selected.append((position, row, available_at))
            step += 1
            family_counts[str(row.get("family") or row.get("arm") or "unknown")] += 1
            if step in checkpoints:
                result.append(self._checkpoint(step, [item[1] for item in selected]))
                observed_snapshots[str(step)] = {
                    key: list(values) for key, values in observed.items()
                }
                pool_snapshots[str(step)] = [
                    row.get("alpha_id") for row in self.pool
                    if (_finite(row.get("pool_entered_at")) is None
                        or _finite(row.get("pool_entered_at")) <= decision_time)
                ]
        if not result and selected:
            result.append(self._checkpoint(len(selected), [item[1] for item in selected]))
            observed_snapshots[str(len(selected))] = {
                key: list(values) for key, values in observed.items()
            }
            pool_snapshots[str(len(selected))] = [
                row.get("alpha_id") for row in self.pool
                if (_finite(row.get("pool_entered_at")) is None
                    or _finite(row.get("pool_entered_at")) <= decision_time)
            ]
        selected_rows = [row for _, row, _ in selected]
        return {"strategy": strategy, "checkpoints": result,
                "selected_proposal_ids": [row.get("proposal_id") for row in selected_rows],
                "observed_history_at_checkpoints": observed_snapshots,
                "pool_snapshot_at_checkpoints": pool_snapshots}

    def compare_rewards(self):
        return {
            "reward_v1": sum(_finite(row.get("reward")) or 0.0 for row in self.candidates),
            "reward_v2": sum(_finite(row.get("reward_v2")) or 0.0 for row in self.candidates),
        }

    @staticmethod
    def _checkpoint(n, rows):
        rewards = [_finite(row.get("reward")) for row in rows]
        rewards = [value for value in rewards if value is not None]
        return {
            "n": n,
            "reward_at_n": sum(rewards),
            "promising_at_n": sum(bool(row.get("promising")) for row in rows),
            "stable_at_n": sum(bool(row.get("stable")) for row in rows),
            "unique_structures_at_n": len({row.get("structural_fingerprint") for row in rows
                                           if row.get("structural_fingerprint")}),
        }


def calibrate_replay(candidates, *, checkpoints=(10, 25, 50, 100)):
    """Compare a declared small grid without modifying historical evidence."""
    replay = SearchPolicyReplay(candidates)
    parameter_rows = []
    for exploration in (0.5, 1.0, 1.5):
        result = replay.run(strategy="current", exploration=exploration,
                            family_penalty=0.05, checkpoints=checkpoints)
        parameter_rows.append({"exploration": exploration, "result": result})
    selected = max(
        parameter_rows,
        key=lambda row: (row["result"]["checkpoints"][-1]["reward_at_n"]
                         if row["result"]["checkpoints"] else 0.0),
    )
    penalties = {}
    for name, penalty in (("none", 0.0), ("weak", 0.025), ("current", 0.05)):
        penalties[name] = replay.run(strategy="current", exploration=selected["exploration"],
                                      family_penalty=penalty, checkpoints=checkpoints)
    return {
        "tested_parameters": [row["exploration"] for row in parameter_rows],
        "selection_metric": "reward_at_n",
        "selected_parameter": selected["exploration"],
        "exploration_grid": parameter_rows,
        "family_penalty_comparison": penalties,
        "baseline_fifo": replay.run(strategy="fifo", checkpoints=checkpoints),
        "current_policy": selected["result"],
    }
