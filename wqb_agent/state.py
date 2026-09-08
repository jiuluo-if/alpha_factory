"""ROLE: CORE
AGENT_RELEVANCE: HIGH
PURPOSE: Represent auditable experiments and append-only recovery evidence.
READ WHEN: changing experiment serialization, trajectory, or checkpoints.
DO NOT USE FOR: treating derived memory as immutable platform truth.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields as dataclass_fields

from .expression import canonical_expression
from .schema import TRAJECTORY_VERSION, CREATED_BY_VERSION


ACTIVE_EXECUTION_STATUSES = frozenset({"PENDING", "RUNNING", "SUBMITTING"})
UNKNOWN_STATUSES = frozenset({"SUBMIT_UNKNOWN", "UNKNOWN"})
UNRESOLVED_STATUSES = ACTIVE_EXECUTION_STATUSES | UNKNOWN_STATUSES
# ``SUBMIT_UNKNOWN`` is intentionally excluded: it requires read-only
# reconciliation, while ordinary UNKNOWN jobs may still be polled/recovered.
RECOVERABLE_STATUSES = ACTIVE_EXECUTION_STATUSES | frozenset({"UNKNOWN"})
TERMINAL_STATUSES = frozenset({"DONE", "FAILED", "SKIPPED", "SKIPPED_STALE", "SKIPPED_UNKNOWN"})

def dataset_ref(value):
    """数据集条目归一化为字符串 id。

    proposal 的 datasets 允许 ``{"id": "pv1", "name": ...}`` 字典形态，
    但 trajectory 去重、ResearchState 聚合等消费方要求数据集是可哈希
    字符串；在 Experiment 入口单点归一化（dict 取 id，缺 id 退化 name）。
    """
    if isinstance(value, dict):
        value = value.get("id") or value.get("name")
    return str(value) if value is not None else None


@dataclass
class Experiment:
    round: int
    hypothesis_id: str
    expression: str
    settings: dict
    fields_used: list
    datasets: list | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    candidate_id: object = None
    proposal_id: object = None
    submission_fingerprint: object = None
    submission_started_at: object = None
    field_source: object = None
    field_understanding: object = None
    field_analysis: object = None
    field_hypothesis_basis: object = None
    operator_evidence: object = None
    template_id: object = None
    template_family: object = None
    template_stage_path: object = None
    template_ref: object = None
    template_slots: object = None
    search_evidence: object = None
    search_outcome: object = None
    provisional_outcome: object = None
    final_outcome: object = None
    robustness_evidence: object = None
    incremental_evidence: object = None
    pnl_evidence: object = None
    research_classification: object = None
    research_evidence_bundle: object = None
    submission_eligibility: object = None
    novelty_score: object = None
    allocation_arm: object = None
    allocation_key: object = None
    factory_session_id: object = None
    self_correlation: object = None
    status: str = "PENDING"
    metrics: object = None
    error: object = None
    alpha_id: object = None
    progress_url: object = None
    skip_record: object = None
    mutation: object = None
    lineage_id: object = None
    experiment_stage: object = None
    research_role: object = None
    change_type: object = None
    parent_expression: object = None
    changed_variable: object = None
    expected_failure_modes: list = field(default_factory=list)
    tuning_risk: object = None
    rationale: object = None
    direction: object = None
    economic_mechanism: object = None
    direction_transform: object = None
    self_correlation_impact: object = None
    expected_horizon: object = None
    falsification: object = None
    health: object = None
    yearly_evidence: object = None
    validation_plan: object = None
    validation_report: object = None
    validation_status: object = None
    elapsed_sec: object = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        self.settings = dict(self.settings)
        self.fields_used = list(self.fields_used)
        self.datasets = [
            ref for ref in (dataset_ref(item) for item in (self.datasets or []))
            if ref
        ]
        self.expected_failure_modes = list(self.expected_failure_modes or [])

    def to_dict(self):
        data = {
            "schema_version": TRAJECTORY_VERSION,
            "created_by_version": CREATED_BY_VERSION,
        }
        data.update({item.name: getattr(self, item.name) for item in dataclass_fields(self)})
        return data

    @classmethod
    def from_dict(cls, data):
        exp = cls(
            data["round"], data["hypothesis_id"], data["expression"],
            data["settings"], data["fields_used"], data.get("datasets"),
        )
        field_names = {item.name for item in dataclass_fields(cls)}
        for name in field_names:
            if name in {"round", "hypothesis_id", "expression", "settings", "fields_used", "datasets"}:
                continue
            if name in data:
                setattr(exp, name, data[name])
        exp.id = data["id"]
        exp.status = data["status"]
        exp.expected_failure_modes = data.get("expected_failure_modes") or []
        exp.created_at = data.get("created_at", 0)
        return exp


class Trajectory:
    """Append-only JSONL history + in-memory recent window.

    The full history is always preserved on disk (trajectory.jsonl);
    memory keeps only the last `max_len` experiments for iteration context.
    """

    COMPLETED_EXPRESSION_CACHE_MAX = 512

    def __init__(self, max_len=100, path=None):
        self.experiments = []
        try:
            self.max_len = max(1, int(max_len))
        except (TypeError, ValueError):
            self.max_len = 100
        self.path = path
        self._recent_ids = set()
        self._completed_expression_cache = {}
        self._append_batch_scope = None
        self._append_batch_known = None

    def add(self, experiment):
        """Append one experiment with cross-restart exactly-once protection."""
        self.add_many([experiment])

    def add_many(self, experiments):
        """Append a batch after one streaming ID reconciliation.

        ``_recent_ids`` is intentionally bounded with the in-memory window,
        so it cannot prove that an old experiment was not already appended
        before a restart.  Reconcile the small incoming batch against the
        append-only file once, then append only unseen rows.  No persistent
        ID sidecar or unbounded in-memory index is created.
        """
        experiments = list(experiments or [])
        if not experiments:
            return []
        candidate_ids = {experiment.id for experiment in experiments}
        known_ids = candidate_ids & self._recent_ids
        scoped_ids = set()
        if self._append_batch_scope is not None:
            scoped_ids = candidate_ids & self._append_batch_scope
            known_ids.update(scoped_ids & (self._append_batch_known or set()))
        if self.path:
            uncached_ids = candidate_ids - known_ids - scoped_ids
            if uncached_ids:
                known_ids.update(self.contains_ids(uncached_ids))
        added = []
        to_persist = []
        for experiment in experiments:
            if experiment.id in known_ids:
                continue
            self.experiments.append(experiment)
            self._recent_ids.add(experiment.id)
            known_ids.add(experiment.id)
            if experiment.id in scoped_ids:
                self._append_batch_known.add(experiment.id)
            self._completed_expression_cache.clear()
            if self.path:
                to_persist.append(experiment)
            added.append(experiment)
        if self.path and to_persist:
            self._append_jsonl_many(to_persist)
        if len(self.experiments) > self.max_len:
            self.experiments = self.experiments[-self.max_len:]
            self._recent_ids = {e.id for e in self.experiments}
        return added

    def begin_append_batch(self, experiments):
        """Reconcile one incoming simulation batch against history once."""
        scope = {
            experiment.id for experiment in (experiments or [])
            if getattr(experiment, "id", None)
        }
        known = scope & self._recent_ids
        if self.path and scope - known:
            known.update(self.contains_ids(scope - known))
        self._append_batch_scope = scope
        self._append_batch_known = known

    def end_append_batch(self):
        """Release transient batch identities after callbacks finish."""
        self._append_batch_scope = None
        self._append_batch_known = None

    def _append_jsonl(self, experiment):
        self._append_jsonl_many([experiment])

    def _append_jsonl_many(self, experiments):
        """Append a batch with one flush/fsync while preserving JSONL order."""
        if not experiments:
            return
        with open(self.path, "a", encoding="utf-8") as f:
            for experiment in experiments:
                f.write(json.dumps(experiment.to_dict(), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def contains_id(self, experiment_id):
        """Check an append-only trajectory id without materializing history."""
        return experiment_id in self.contains_ids({experiment_id})

    def contains_ids(self, experiment_ids):
        """Find a set of IDs in one streaming pass over trajectory."""
        if isinstance(experiment_ids, (str, int)):
            experiment_ids = {experiment_ids}
        targets = {value for value in (experiment_ids or set()) if value}
        if not targets or not self.path or not os.path.exists(self.path):
            return set()
        found = set()
        try:
            with open(self.path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(row, dict) and row.get("id") in targets:
                        found.add(row["id"])
                        if found == targets:
                            break
        except OSError:
            return set()
        return found

    def iter_ids(self):
        """Stream trajectory ids without constructing Experiment objects."""
        for row in self.iter_rows() or ():
            if row.get("id"):
                yield row["id"]

    def iter_rows(self):
        """Stream valid raw trajectory objects without retaining history.

        This is a read-only primitive for bounded identity/audit passes.  It
        deliberately yields dictionaries rather than ``Experiment`` objects
        so callers do not materialize the day-long append-only file or create
        a persistent sidecar index.
        """
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(row, dict):
                        yield row
        except OSError:
            return

    def find_completed_expression(self, expression):
        """Find a completed experiment by streaming the append-only history.

        The in-memory trajectory is intentionally bounded. Older parents must
        still be available for proposal validation without loading the whole
        day-long JSONL file into memory.
        """
        if not self.path or not expression or not os.path.exists(self.path):
            return None
        target = canonical_expression(expression)
        return self.find_completed_expressions([target]).get(target)

    def find_completed_expressions(self, expressions):
        """Resolve several old parents with one streaming history pass.

        Proposal batches commonly validate multiple CHILD/ROBUSTNESS entries.
        Reading the append-only trajectory once per parent makes that gate
        scale with the batch, while the bounded cache retains repeat-call
        idempotency without creating a new sidecar index.
        """
        targets = {
            canonical_expression(expression)
            for expression in (expressions or [])
            if isinstance(expression, str) and expression.strip()
        }
        if not targets or not self.path or not os.path.exists(self.path):
            return {}
        pending = targets - self._completed_expression_cache.keys()
        found = {}
        if pending:
            try:
                with open(self.path, encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            row = json.loads(line)
                            if not isinstance(row, dict):
                                continue
                            target = canonical_expression(row.get("expression", ""))
                            if target not in pending:
                                continue
                            if row.get("status") != "DONE" or not row.get("metrics"):
                                continue
                            found[target] = Experiment.from_dict(row)
                        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                            continue
            except OSError:
                pass
            self._completed_expression_cache.update(
                {target: found.get(target) for target in pending}
            )
            overflow = (
                len(self._completed_expression_cache)
                - self.COMPLETED_EXPRESSION_CACHE_MAX
            )
            if overflow > 0:
                for target in list(self._completed_expression_cache)[:overflow]:
                    self._completed_expression_cache.pop(target, None)
        return {
            target: self._completed_expression_cache.get(target)
            for target in targets
        }

    def load(self):
        """Load trajectory.jsonl. Only the last ``max_len`` lines are parsed
        into memory (the full history stays on disk); a big history therefore
        never slows down startup or dedupe."""
        if self.path and os.path.exists(self.path):
            loaded = []
            for line in self._tail_lines(self.max_len):
                line = line.strip()
                if not line:
                    continue
                try:
                    loaded.append(Experiment.from_dict(json.loads(line)))
                except (ValueError, KeyError, TypeError):
                    continue
            self.experiments = loaded[-self.max_len:]
            self._recent_ids = {e.id for e in self.experiments}
            self._completed_expression_cache.clear()
        return self

    def _tail_lines(self, n):
        """Read the last up-to-``n`` lines under a hard byte ceiling.

        Normal trajectory rows are small, but a malformed or unexpectedly
        large row must not make an all-day restart allocate the whole history.
        Returning fewer rows is safer than unbounded memory growth; the raw
        append-only file remains untouched for later reconciliation.
        """
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                chunks = []
                newline_count = 0
                bytes_read = 0
                max_bytes = 64 * 1024 * 1024
                while pos > 0 and newline_count <= n and bytes_read < max_bytes:
                    size = min(1024 * 1024, pos)
                    size = min(size, max_bytes - bytes_read)
                    pos -= size
                    f.seek(pos)
                    chunk = f.read(size)
                    chunks.append(chunk)
                    bytes_read += len(chunk)
                    newline_count += chunk.count(b"\n")
        except OSError:
            return []
        data = b"".join(reversed(chunks))
        decoded = [ln.decode("utf-8", errors="replace") for ln in data.splitlines()[-n:]]
        return [ln for ln in decoded if ln.strip()]

    def recent(self, n=20):
        return self.experiments[-n:]

    def completed(self):
        return [e for e in self.experiments if e.metrics is not None]

    def expressions(self):
        return {e.expression for e in self.experiments}

    def to_dict(self):
        return {"experiments": [e.to_dict() for e in self.experiments]}

    @classmethod
    def from_dict(cls, data, max_len=100):
        traj = cls(max_len=max_len)
        traj.experiments = [Experiment.from_dict(e) for e in data.get("experiments", [])]
        traj.experiments = traj.experiments[-traj.max_len:]
        traj._recent_ids = {e.id for e in traj.experiments}
        traj._completed_expression_cache.clear()
        return traj


class ResearchState:
    def __init__(self, round_no=0, hypothesis=None, dataset=None, fields_used=None):
        self.round_no = round_no
        self.hypothesis = hypothesis
        self.dataset = dataset
        self.fields_used = fields_used or []
        self.started_at = time.time()

    def to_dict(self):
        return {
            "round_no": self.round_no,
            "hypothesis": self.hypothesis,
            "dataset": self.dataset,
            "fields_used": self.fields_used,
            "started_at": self.started_at,
        }
