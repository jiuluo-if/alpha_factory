import json
import os
import time
import uuid

from .expression import canonical_expression

def dataset_ref(value):
    """数据集条目归一化为字符串 id。

    proposal 的 datasets 允许 ``{"id": "pv1", "name": ...}`` 字典形态，
    但 trajectory 去重、ResearchState 聚合等消费方要求数据集是可哈希
    字符串；在 Experiment 入口单点归一化（dict 取 id，缺 id 退化 name）。
    """
    if isinstance(value, dict):
        value = value.get("id") or value.get("name")
    return str(value) if value is not None else None


class Experiment:
    def __init__(
        self, round_no, hypothesis_id, expression, settings, fields_used,
        datasets=None,
    ):
        self.id = uuid.uuid4().hex[:12]
        self.candidate_id = None
        self.proposal_id = None
        self.submission_fingerprint = None
        self.submission_started_at = None
        self.field_source = None
        self.field_understanding = None
        self.field_analysis = None
        self.field_hypothesis_basis = None
        self.operator_evidence = None
        self.template_id = None
        self.template_family = None
        self.template_stage_path = None
        self.template_ref = None
        self.template_slots = None
        self.search_evidence = None
        self.novelty_score = None
        self.allocation_arm = None
        self.allocation_key = None
        self.factory_session_id = None
        self.self_correlation = None
        self.round = round_no
        self.hypothesis_id = hypothesis_id
        self.expression = expression
        self.settings = dict(settings)
        self.fields_used = list(fields_used)
        refs = [dataset_ref(d) for d in (datasets or [])]
        self.datasets = [r for r in refs if r]
        self.status = "PENDING"
        self.metrics = None
        self.error = None
        self.alpha_id = None
        # Persisted immediately after a successful POST.  On resume, the
        # scheduler polls this URL instead of submitting the expression again.
        self.progress_url = None
        # Transport-only terminal outcome after repeated read-only stale
        # reconciliation.  It is never a research-quality conclusion.
        self.skip_record = None
        self.mutation = None
        # Persist the proposal design so a result is traceable to one
        # baseline or one explicit variable change.
        self.lineage_id = None
        self.experiment_stage = None
        self.change_type = None
        self.parent_expression = None
        self.changed_variable = None
        self.expected_failure_modes = []
        self.tuning_risk = None
        self.rationale = None
        self.direction = None
        self.expected_horizon = None
        self.falsification = None
        self.health = None
        # Optional read-only annual aggregate evidence.  Missing in legacy
        # rows is intentionally compatible and remains UNKNOWN.
        self.yearly_evidence = None
        # A robustness plan is registered before its jobs are submitted.
        self.validation_plan = None
        self.validation_report = None
        # Only an explicit robustness procedure may set this to STABLE.
        # Unset means the record is evidence, not a promotable champion.
        self.validation_status = None
        self.elapsed_sec = None
        self.created_at = time.time()

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "proposal_id": self.proposal_id,
            "submission_fingerprint": self.submission_fingerprint,
            "submission_started_at": self.submission_started_at,
            "field_source": self.field_source,
            "field_understanding": self.field_understanding,
            "field_analysis": self.field_analysis,
            "field_hypothesis_basis": self.field_hypothesis_basis,
            "operator_evidence": self.operator_evidence,
            "template_id": self.template_id,
            "template_family": self.template_family,
            "template_stage_path": self.template_stage_path,
            "template_ref": self.template_ref,
            "template_slots": self.template_slots,
            "search_evidence": self.search_evidence,
            "novelty_score": self.novelty_score,
            "allocation_arm": self.allocation_arm,
            "allocation_key": self.allocation_key,
            "factory_session_id": self.factory_session_id,
            "self_correlation": self.self_correlation,
            "round": self.round,
            "hypothesis_id": self.hypothesis_id,
            "expression": self.expression,
            "settings": self.settings,
            "fields_used": self.fields_used,
            "datasets": self.datasets,
            "status": self.status,
            "metrics": self.metrics,
            "error": self.error,
            "alpha_id": self.alpha_id,
            "progress_url": self.progress_url,
            "skip_record": self.skip_record,
            "mutation": self.mutation,
            "lineage_id": self.lineage_id,
            "experiment_stage": self.experiment_stage,
            "change_type": self.change_type,
            "parent_expression": self.parent_expression,
            "changed_variable": self.changed_variable,
            "expected_failure_modes": self.expected_failure_modes,
            "tuning_risk": self.tuning_risk,
            "rationale": self.rationale,
            "direction": self.direction,
            "expected_horizon": self.expected_horizon,
            "falsification": self.falsification,
            "health": self.health,
            "yearly_evidence": self.yearly_evidence,
            "validation_plan": self.validation_plan,
            "validation_report": self.validation_report,
            "validation_status": self.validation_status,
            "elapsed_sec": self.elapsed_sec,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data):
        exp = cls(
            data["round"],
            data["hypothesis_id"],
            data["expression"],
            data["settings"],
            data["fields_used"],
            data.get("datasets"),
        )
        exp.id = data["id"]
        exp.candidate_id = data.get("candidate_id")
        exp.proposal_id = data.get("proposal_id")
        exp.submission_fingerprint = data.get("submission_fingerprint")
        exp.submission_started_at = data.get("submission_started_at")
        exp.field_source = data.get("field_source")
        exp.field_understanding = data.get("field_understanding")
        exp.field_analysis = data.get("field_analysis")
        exp.field_hypothesis_basis = data.get("field_hypothesis_basis")
        exp.operator_evidence = data.get("operator_evidence")
        exp.template_id = data.get("template_id")
        exp.template_family = data.get("template_family")
        exp.template_stage_path = data.get("template_stage_path")
        exp.template_ref = data.get("template_ref")
        exp.template_slots = data.get("template_slots")
        exp.search_evidence = data.get("search_evidence")
        exp.novelty_score = data.get("novelty_score")
        exp.allocation_arm = data.get("allocation_arm")
        exp.allocation_key = data.get("allocation_key")
        exp.factory_session_id = data.get("factory_session_id")
        exp.self_correlation = data.get("self_correlation")
        exp.status = data["status"]
        exp.metrics = data.get("metrics")
        exp.error = data.get("error")
        exp.alpha_id = data.get("alpha_id")
        exp.progress_url = data.get("progress_url")
        exp.skip_record = data.get("skip_record")
        exp.mutation = data.get("mutation")
        exp.lineage_id = data.get("lineage_id")
        exp.experiment_stage = data.get("experiment_stage")
        exp.change_type = data.get("change_type")
        exp.parent_expression = data.get("parent_expression")
        exp.changed_variable = data.get("changed_variable")
        exp.expected_failure_modes = data.get("expected_failure_modes") or []
        exp.tuning_risk = data.get("tuning_risk")
        exp.rationale = data.get("rationale")
        exp.direction = data.get("direction")
        exp.expected_horizon = data.get("expected_horizon")
        exp.falsification = data.get("falsification")
        exp.health = data.get("health")
        exp.yearly_evidence = data.get("yearly_evidence")
        exp.validation_plan = data.get("validation_plan")
        exp.validation_report = data.get("validation_report")
        exp.validation_status = data.get("validation_status")
        exp.elapsed_sec = data.get("elapsed_sec")
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
