"""Phase-3 search policy: structural, empirical and budget diversity.

The module is deliberately transport/persistence free.  It consumes proposal
and result dictionaries, so the production submission path remains owned by
``Agent`` and ``Simulator``.
"""

from collections import Counter, defaultdict
import math
import re


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[^\s]")
_OPERATOR_WORDS = {
    "rank", "zscore", "ts_mean", "ts_sum", "ts_std_dev", "ts_rank",
    "ts_zscore", "ts_delta", "ts_decay_linear", "delta", "delay",
    "group_neutralize", "group_rank", "scale", "log", "abs", "sign",
    "sqrt", "min", "max", "add", "sub", "mul", "div", "and", "or",
}


def _get(record, key, default=None):
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _field_ids(record):
    values = _get(record, "fields_used", None) or _get(record, "fields", None) or []
    result = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("id")
        if isinstance(value, (str, int)) and str(value):
            result.append(str(value).lower())
    return result


def structural_fingerprint(expression, fields=None):
    """Normalize an expression into an AST-like token fingerprint.

    This is intentionally a bounded tokenizer rather than a platform parser:
    it distinguishes operator/window/arity structure, anonymizes known fields,
    and never executes or evaluates user supplied expressions.
    """
    known = {str(item).lower() for item in (fields or [])}
    out = []
    for token in _TOKEN_RE.findall(str(expression or "").lower()):
        if token in known:
            out.append("<field>")
        elif re.fullmatch(r"\d+(?:\.\d+)?", token):
            out.append("<number>")
        elif re.fullmatch(r"[a-z_][a-z0-9_]*", token):
            out.append(token if token in _OPERATOR_WORDS else "<identifier>")
        else:
            out.append(token)
    return " ".join(out)


def subtree_fingerprints(expression, fields=None):
    """Return bounded contiguous subtrees useful for repeat penalties."""
    tokens = structural_fingerprint(expression, fields).split()
    result = set()
    for width in (2, 3, 4, 5):
        result.update(" ".join(tokens[i:i + width]) for i in range(max(0, len(tokens) - width + 1)))
    return frozenset(result)


def syntax_diversity(record, pool):
    current = structural_fingerprint(_get(record, "expression", ""), _field_ids(record))
    other = [structural_fingerprint(_get(item, "expression", ""), _field_ids(item)) for item in pool]
    if not other:
        return {"status": "NO_POOL", "nearest": None, "score": 1.0}
    distances = [0.0 if current == item else 1.0 for item in other]
    nearest = min(distances)
    return {"status": "AVAILABLE", "nearest": 1.0 - nearest, "score": nearest}


def _series(record):
    for key in ("returns", "pnl", "pnl_series", "signal_returns"):
        value = _get(record, key)
        if isinstance(value, (list, tuple)):
            clean = []
            for item in value:
                try:
                    value_f = float(item)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value_f):
                    clean.append(value_f)
            if len(clean) >= 3:
                return clean
    return None


def _corr(left, right):
    n = min(len(left), len(right))
    if n < 3:
        return None
    a, b = left[:n], right[:n]
    ma, mb = sum(a) / n, sum(b) / n
    da = sum((x - ma) ** 2 for x in a)
    db = sum((y - mb) ** 2 for y in b)
    if da <= 0 or db <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(da * db)


def empirical_pool_summary(record, pool):
    """Measure behavioral redundancy and incremental value against a pool."""
    current = _series(record)
    correlations = []
    if current:
        for item in pool:
            other = _series(item)
            value = _corr(current, other) if other else None
            if value is not None:
                correlations.append(value)
    if not correlations:
        return {
            "status": "UNAVAILABLE", "max_corr": None, "median_corr": None,
            "nearest_corr": None, "incremental_value": None,
        }
    ordered = sorted(correlations)
    median = ordered[len(ordered) // 2]
    max_corr = max(correlations)
    # Incremental value is a conservative residual proxy: highly correlated
    # returns add little new information; no regression is claimed here.
    incremental = max(0.0, 1.0 - max(abs(value) for value in correlations))
    return {
        "status": "AVAILABLE", "max_corr": max_corr,
        "median_corr": median, "nearest_corr": max_corr,
        "incremental_value": incremental,
    }


def incremental_novelty(record, pool):
    """Combine syntax and empirical novelty without hiding unavailable data."""
    syntax = syntax_diversity(record, pool)
    empirical = empirical_pool_summary(record, pool)
    field_sets = [set(_field_ids(item)) for item in pool]
    fields = set(_field_ids(record))
    field_overlap = max((len(fields & other) / len(fields | other) for other in field_sets if fields or other), default=0.0)
    empirical_score = empirical["incremental_value"]
    if empirical_score is None:
        score = 0.7 * syntax["score"] + 0.3 * (1.0 - field_overlap)
    else:
        score = 0.4 * syntax["score"] + 0.2 * (1.0 - field_overlap) + 0.4 * empirical_score
    return {"score": round(max(0.0, min(1.0, score)), 6), "syntax": syntax,
            "empirical": empirical, "field_overlap": round(field_overlap, 6)}


def pareto_front(records):
    """Return non-dominated records over quality and novelty dimensions."""
    dimensions = ("sharpe", "fitness", "turnover", "margin", "drawdown", "novelty")
    maximize = {"sharpe", "fitness", "margin", "novelty"}

    def value(record, key):
        raw = _get(record, key)
        if raw is None and key == "novelty":
            raw = _get(record, "novelty_score", 0.0)
        try:
            parsed = float(raw)
            return parsed if math.isfinite(parsed) else None
        except (TypeError, ValueError):
            return None

    valid = []
    for record in records or []:
        metrics = _get(record, "metrics", {}) or {}
        row = dict(record) if isinstance(record, dict) else {key: _get(record, key) for key in dimensions}
        for key in dimensions:
            row.setdefault(key, metrics.get(key))
        if any(value(row, key) is None for key in dimensions):
            continue
        valid.append((record, row))
    front = []
    for candidate, row in valid:
        dominated = False
        for other, other_row in valid:
            if other is candidate:
                continue
            no_worse = True
            strictly_better = False
            for key in dimensions:
                left, right = value(other_row, key), value(row, key)
                if key in maximize:
                    no_worse &= left >= right
                    strictly_better |= left > right
                else:
                    no_worse &= left <= right
                    strictly_better |= left < right
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    return front


class BudgetAllocator:
    """Small UCB allocator for dataset-family × mechanism-family arms."""

    def __init__(self, total_budget=100, exploration=1.0, max_pending_per_arm=1):
        self.total_budget = max(0, int(total_budget))
        self.exploration = float(exploration)
        self.max_pending_per_arm = max(1, int(max_pending_per_arm))
        self.arms = defaultdict(lambda: {"completed": 0, "pending": 0, "unknown": 0, "reserved": 0, "reward": 0.0})

    @staticmethod
    def arm_key(proposal):
        dataset = _get(proposal, "dataset_family") or _get(proposal, "datasets") or "unknown-dataset"
        mechanism = _get(proposal, "mechanism_family") or _get(proposal, "template_family") or "unknown-mechanism"
        if isinstance(dataset, (list, tuple)):
            dataset = "+".join(sorted(str(item) for item in dataset))
        return f"{dataset}::{mechanism}"

    def _state(self, arm):
        return self.arms[self.arm_key(arm) if isinstance(arm, dict) else str(arm)]

    def can_reserve(self, proposal):
        state = self._state(proposal)
        return state["pending"] + state["unknown"] + state["reserved"] < self.max_pending_per_arm

    def reserve(self, proposal):
        if not self.can_reserve(proposal):
            return False
        self._state(proposal)["reserved"] += 1
        return True

    def complete(self, proposal, reward=0.0):
        state = self._state(proposal)
        state["reserved"] = max(0, state["reserved"] - 1)
        state["pending"] = max(0, state["pending"] - 1)
        state["unknown"] = max(0, state["unknown"] - 1)
        state["completed"] += 1
        try:
            state["reward"] += float(reward)
        except (TypeError, ValueError):
            pass

    def mark_pending(self, proposal):
        state = self._state(proposal)
        state["reserved"] = max(0, state["reserved"] - 1)
        state["pending"] += 1

    def mark_unknown(self, proposal):
        state = self._state(proposal)
        state["reserved"] = max(0, state["reserved"] - 1)
        state["unknown"] += 1

    def score(self, proposal):
        state = self._state(proposal)
        count = state["completed"]
        total = sum(item["completed"] for item in self.arms.values())
        if count == 0:
            return self.exploration + (1.0 if total else 0.0)
        mean = state["reward"] / count
        bonus = self.exploration * math.sqrt(math.log(max(2, total + 1)) / count)
        return mean + bonus

    def snapshot(self):
        return {key: dict(value) for key, value in self.arms.items()}


class SearchPolicy:
    """Extensible policy facade; MCTS is intentionally reserved for later."""

    def __init__(self, config=None):
        config = config or {}
        self.enabled = bool(config.get("enabled", False))
        self.max_pending_per_arm = max(1, int(config.get("max_pending_per_arm", 1)))
        self.allocator = BudgetAllocator(
            config.get("max_simulations", 100), config.get("ucb_exploration", 1.0),
            self.max_pending_per_arm,
        )
        self.subtree_counts = Counter()
        self.family_counts = Counter()

    def annotate(self, proposal, pool):
        evidence = incremental_novelty(proposal, pool)
        proposal["search_evidence"] = evidence
        proposal["novelty_score"] = evidence["score"]
        return proposal

    def priority(self, proposal):
        if not self.enabled:
            return 0.0
        evidence = proposal.get("search_evidence") or {}
        novelty = float(proposal.get("novelty_score", evidence.get("score", 0.0)))
        penalty = 0.05 * self.family_counts[proposal.get("template_family")]
        return novelty + self.allocator.score(proposal) - penalty

    def accept(self, proposal):
        if not self.enabled:
            return True
        return self.allocator.reserve(proposal)

    def release(self, proposal, status="DONE", reward=0.0):
        if status == "DONE":
            self.allocator.complete(proposal, reward)
        elif status == "UNKNOWN":
            self.allocator.mark_unknown(proposal)
        else:
            self.allocator.mark_pending(proposal)
