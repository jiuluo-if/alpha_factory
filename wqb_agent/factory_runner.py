"""ROLE: LEGACY
AGENT_RELEVANCE: LOW
PURPOSE: Preserve compatibility for the existing bounded factory lifecycle.
READ WHEN: a factory command or legacy session must be maintained.
DO NOT USE FOR: the default agent-facing research model or new experiments.

Unattended, bounded Alpha-factory orchestration.

The runner is intentionally thin: Agent remains the only owner of BRAIN
submission, checkpoint recovery, reflection, and research state.  This module
adds a session envelope and a deterministic template proposal adapter, so a
day-long process reuses the same canonical artifacts instead of creating one
control file per pass.
"""

import json
import os
import re
import time
import uuid
from contextlib import redirect_stdout

from .artifacts import atomic_write_json_if_changed
from .expression import canonical_expression
from .schema import CREATED_BY_VERSION, CHECKPOINT_VERSION


class _DiscardWriter:
    """Drop quiet factory output without retaining a round-sized buffer."""

    def write(self, value):
        return len(value)

    def flush(self):
        return None


_DISCARD_STDOUT = _DiscardWriter()


class AIFactoryRunner:
    """Run suggestion -> proposal assembly -> production execution repeatedly."""

    SESSION_FILE = "factory_session.json"
    CHECKPOINT_CACHE_MAX = 512

    @classmethod
    def read_session(cls, state_dir):
        """Read the single factory envelope without constructing an Agent."""
        path = os.path.join(state_dir, cls.SESSION_FILE)
        try:
            with open(path, encoding="utf-8") as handle:
                session = json.load(handle)
            if not isinstance(session, dict) or not isinstance(session.get("session_id"), str):
                return None
            return session
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    @classmethod
    def request_stop(cls, state_dir):
        """Set a durable stop request in the canonical session envelope."""
        session = cls.read_session(state_dir)
        if not session or session.get("status") != "RUNNING":
            return None
        try:
            float(session["deadline"])
        except (KeyError, TypeError, ValueError):
            return None
        session["stop_requested"] = True
        session["last_action"] = "STOP_REQUESTED"
        atomic_write_json_if_changed(
            os.path.join(state_dir, cls.SESSION_FILE), session,
            ignored_keys=("updated_at",),
        )
        return session

    @classmethod
    def status_view(cls, state_dir):
        """Return only the stable, decision-useful session fields."""
        session = cls.read_session(state_dir)
        if not session:
            if os.path.exists(os.path.join(state_dir, cls.SESSION_FILE)):
                return {
                    "status": "RECONCILE_REQUIRED",
                    "last_action": "INVALID_SESSION",
                }
            return None
        keys = (
            "schema_version", "session_id", "started_at", "deadline", "status",
            "stop_requested", "rounds_completed", "simulations_reserved",
            "simulation_cap", "last_round", "last_action", "last_result",
        )
        view = {key: session[key] for key in keys if key in session}
        if isinstance(view.get("last_result"), dict):
            view["last_result"] = {
                key: view["last_result"][key]
                for key in ("round_no", "proposals", "summary_round", "verdicts", "best",
                            "status", "error_type", "message")
                if key in view["last_result"]
            }
        return view

    def __init__(self, agent, *, factory=None, clock=None, sleeper=None, quiet=True):
        self.agent = agent
        self.factory = factory or agent.alpha_factory
        self._clock = clock or time.time
        self._sleep = sleeper or time.sleep
        self.quiet = bool(quiet)
        self.state_dir = agent.state_dir
        self.session_path = os.path.join(self.state_dir, self.SESSION_FILE)
        self.proposals_path = os.path.join(self.state_dir, "proposals.json")
        # Completed checkpoint names are monotonic within a process. Cache
        # only this tiny control-plane fact; unfinished/malformed files are
        # always re-read so recovery and reconciliation remain fail-closed.
        # Cache completed checkpoint reads only while the file signature is
        # unchanged. A changed file must be re-read: a stale name-only cache
        # could miss a newly unfinished checkpoint after repair/replacement.
        self._complete_checkpoint_signatures = {}

    def run(self, duration_sec=86400, max_rounds=0, idle_sleep_sec=30,
            max_simulations=240):
        # RESEARCH_POLICY:
        # This compatibility loop is not the default agent-facing model;
        # safety boundaries inside Agent and Client remain mechanism.
        """Run until the deadline or round cap; return a compact session view.

        ``max_rounds=0`` means duration-only.  A non-positive duration is a
        safe dry start and performs no discovery or POST.
        """
        try:
            duration = max(0.0, float(duration_sec))
        except (TypeError, ValueError):
            duration = 86400.0
        try:
            round_cap = max(0, int(max_rounds))
        except (TypeError, ValueError):
            round_cap = 0
        try:
            idle = max(1.0, min(60.0, float(idle_sleep_sec)))
        except (TypeError, ValueError):
            idle = 30.0
        try:
            simulation_cap = max(0, int(max_simulations))
        except (TypeError, ValueError):
            simulation_cap = 240
        now = self._clock()
        session = self._load_session()
        # A present but malformed control envelope is evidence, not an empty
        # workspace. Preserve it for manual repair instead of overwriting it
        # with a fresh session that could lose the last execution boundary.
        if session is None and os.path.exists(self.session_path):
            return {
                "schema_version": CHECKPOINT_VERSION,
                "created_by_version": CREATED_BY_VERSION,
                "status": "RECONCILE_REQUIRED",
                "last_action": "INVALID_SESSION",
                "last_result": {"status": "INVALID_SESSION"},
            }
        # A transport-reconciliation terminal state is a safety boundary, not
        # an invitation to silently mint a new session. Starting over here
        # could re-POST an operation whose outcome was never reconciled.
        # Budget exhaustion is different: it is a clean session boundary and
        # a later explicit factory invocation may start a new budget window.
        if session and session.get("status") == "RECONCILE_REQUIRED":
            return session
        # A zero-duration probe must never overwrite or stop a live session.
        # The explicit --factory-stop command is the only control-plane action
        # allowed to request a running factory to stop.
        if duration <= 0 and session and session.get("status") == "RUNNING":
            return session
        if duration <= 0 or not session or session.get("status") != "RUNNING" or session.get("deadline", 0) <= now:
            session = {
                "schema_version": CHECKPOINT_VERSION,
                "created_by_version": CREATED_BY_VERSION,
                "session_id": uuid.uuid4().hex[:16],
                "started_at": now,
                "deadline": now + duration,
                "status": "RUNNING",
                "rounds_completed": 0,
                "simulations_reserved": 0,
                "simulation_cap": simulation_cap,
                "last_round": None,
                "last_action": "START",
                "last_result": None,
            }
        else:
            # A restart resumes the existing deadline and budget.  It must not
            # silently grant another full day or another simulation allowance.
            session.setdefault("simulations_reserved", 0)
            session.setdefault("simulation_cap", simulation_cap)
            session.setdefault("rounds_completed", 0)
            session.setdefault("probe_offset", 0)
        session.setdefault("stop_requested", False)
        self._save_session(session)
        if duration <= 0:
            session["status"] = "STOPPED"
            session["last_action"] = "ZERO_DURATION"
            self._save_session(session)
            return session

        while self._clock() < session["deadline"]:
            # Reload only the small canonical envelope so --factory-stop can
            # control a live process without touching proposals/checkpoints.
            current = self._load_session()
            if current and current.get("session_id") == session.get("session_id"):
                session["stop_requested"] = bool(current.get("stop_requested", False))
            if session.get("stop_requested"):
                session["status"] = "STOPPED"
                session["last_action"] = "STOP_REQUESTED"
                break
            if session.get("last_action") == "PROPOSALS_WRITE_ERROR":
                # The new payload is not durable and the old canonical inbox
                # may belong to another round; do not generate a replacement
                # hypothesis until the storage boundary is reconciled.
                session["status"] = "RECONCILE_REQUIRED"
                session["last_action"] = "STORAGE_RECONCILE_REQUIRED"
                self._save_session(session)
                break
            orphaned_proposals = self._orphaned_canonical_proposals(session)
            if orphaned_proposals:
                proposal_count = len(orphaned_proposals)
                reserved = int(session.get("simulations_reserved", 0))
                gap = max(0, proposal_count - reserved)
                if gap > max(0, int(session.get("simulation_cap", simulation_cap)) - reserved):
                    session["status"] = "SIMULATION_BUDGET_CAP"
                    session["last_action"] = "ORPHANED_PROPOSALS_BUDGET_BLOCKED"
                    session["last_result"] = {
                        "round_no": session.get("last_round"),
                        "proposals": proposal_count,
                        "status": "ORPHANED_PROPOSALS_BUDGET_BLOCKED",
                    }
                    self._save_session(session)
                    break
                session["simulations_reserved"] = reserved + gap
                session["last_action"] = "RECOVER_PROPOSALS"
                self._save_session(session)
                try:
                    result = self._call(self.agent.run_proposals, self.proposals_path)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as exc:
                    if self._stop_on_terminal_error(session, "RECOVER_PROPOSALS", exc):
                        break
                    self._record_retry(session, "RECOVER_PROPOSALS_ERROR", exc)
                    self._save_session(session)
                    self._bounded_sleep(self._retry_delay(idle, session), session["deadline"])
                    continue
                session["retry_count"] = 0
                # A checkpoint created by this call is handled by the normal
                # recovery branch on the next loop; keep its accepted slots.
                if self._unfinished_checkpoint():
                    session["last_action"] = "RECOVER_PROPOSALS_PENDING"
                    self._save_session(session)
                    continue
                accepted = self._accepted_count(proposal_count)
                session["simulations_reserved"] = max(
                    0, int(session.get("simulations_reserved", 0)) - proposal_count + accepted
                )
                session["rounds_completed"] += 1
                session["last_action"] = "RECOVERED_PROPOSALS"
                session["last_result"] = self._compact_result(
                    session.get("last_round"), result, proposal_count
                )
                self._save_session(session)
                continue
            foreign = self._unfinished_checkpoint()
            if (
                session.get("last_action") in {
                    "RUN_PROPOSALS_ERROR", "RECOVER_PROPOSALS_ERROR"
                }
                and not foreign
            ):
                # An exception after the production call has no checkpoint to
                # prove whether a POST happened.  Stop for reconciliation;
                # never re-POST merely because the process is unattended.
                session["status"] = "RECONCILE_REQUIRED"
                session["last_action"] = "EXECUTION_RECONCILE_REQUIRED"
                self._save_session(session)
                break
            if foreign:
                # Recovery is always first.  If the canonical proposal file is
                # absent/mismatched, stop for reconciliation rather than
                # generating a new round that could consume another slot.
                checkpoint_round = self._checkpoint_round(foreign)
                if self._proposal_round() == checkpoint_round:
                    if not self._recovery_already_reserved(session, checkpoint_round):
                        recovery_count = self._checkpoint_experiment_count(foreign)
                        remaining = max(
                            0,
                            int(session.get("simulation_cap", simulation_cap))
                            - int(session.get("simulations_reserved", 0)),
                        )
                        if recovery_count > remaining:
                            session["status"] = "SIMULATION_BUDGET_CAP"
                            session["last_action"] = "RECOVERY_BUDGET_BLOCKED"
                            session["last_result"] = {
                                "round_no": checkpoint_round,
                                "proposals": recovery_count,
                                "status": "RECOVERY_BUDGET_BLOCKED",
                            }
                            self._save_session(session)
                            break
                        session["simulations_reserved"] = (
                            int(session.get("simulations_reserved", 0)) + recovery_count
                        )
                    session["last_action"] = "RECOVER_CHECKPOINT"
                    self._save_session(session)
                    try:
                        recovery_result = self._call(
                            self.agent.run_proposals, self.proposals_path
                        )
                    except (KeyboardInterrupt, SystemExit):
                        raise
                    except Exception as exc:
                        if self._stop_on_terminal_error(session, "RECOVER_CHECKPOINT", exc):
                            break
                        # Recovery is itself a durable operation.  Persist the
                        # retry marker before sleeping so a process restart
                        # continues from the same checkpoint and does not
                        # manufacture a replacement round.
                        self._record_retry(session, "RECOVER_CHECKPOINT_ERROR", exc)
                        self._save_session(session)
                        self._bounded_sleep(self._retry_delay(idle, session), session["deadline"])
                        continue
                    session["retry_count"] = 0
                if self._unfinished_checkpoint():
                    session["status"] = "RECONCILE_REQUIRED"
                    session["last_action"] = "CHECKPOINT_BLOCKED"
                    break
                session["rounds_completed"] += 1
                session["last_action"] = "RECOVERED_CHECKPOINT"
                session["last_result"] = self._compact_result(
                    checkpoint_round, recovery_result, self._checkpoint_experiment_count(foreign)
                )
                self._save_session(session)

            if round_cap and session["rounds_completed"] >= round_cap:
                session["status"] = "ROUND_CAP"
                session["last_action"] = "ROUND_CAP"
                self._save_session(session)
                break
            remaining_budget = max(
                0, int(session.get("simulation_cap", simulation_cap))
                - int(session.get("simulations_reserved", 0))
            )
            if remaining_budget <= 0:
                session["status"] = "SIMULATION_BUDGET_CAP"
                session["last_action"] = "BUDGET_BLOCKED"
                break

            round_no = self.agent.next_round_no()
            try:
                probe_offset = max(0, int(session.get("probe_offset", 0)))
            except (TypeError, ValueError):
                probe_offset = 0
            probe_round = round_no + probe_offset
            session["last_round"] = round_no
            session["last_action"] = "SUGGEST"
            self._save_session(session)
            try:
                bundle = self._call(self.agent.run_suggestion_round, probe_round)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                if self._stop_on_terminal_error(session, "SUGGEST", exc):
                    break
                self._record_retry(session, "SUGGEST_ERROR", exc)
                self._save_session(session)
                self._bounded_sleep(self._retry_delay(idle, session), session["deadline"])
                continue
            if not isinstance(bundle, dict):
                session["probe_offset"] = probe_offset + 1
                session["last_action"] = "WAIT_NO_SUGGESTION"
                self._save_session(session)
                self._bounded_sleep(idle, session["deadline"])
                continue
            session["retry_count"] = 0
            research_space = bundle.get("research_space")
            if not isinstance(research_space, dict):
                session["probe_offset"] = probe_offset + 1
                session["last_action"] = "WAIT_INVALID_SUGGESTION"
                session["last_result"] = {
                    "round_no": round_no,
                    "status": "INVALID_RESEARCH_SPACE",
                }
                self._save_session(session)
                self._bounded_sleep(idle, session["deadline"])
                continue
            raw_tags = research_space.get("tags")
            raw_tags = raw_tags if isinstance(raw_tags, (list, tuple, set)) else []
            hypothesis = {
                "id": research_space.get("id") or f"h-factory-r{round_no}",
                "statement": research_space.get(
                    "statement", "AI factory field mechanism baseline"
                ),
                "tags": [str(tag) for tag in raw_tags if tag is not None] + ["factory"],
                "datasets": self._string_ids(research_space.get("datasets")),
                "field_source": bundle.get("field_source"),
                "template_mode": str(
                    getattr(self.agent, "factory_config", {}).get(
                        "template_mode", "legacy"
                    )
                ).lower(),
            }
            try:
                candidate_cap = min(
                    getattr(self.agent, "max_proposals_per_round", 18),
                    getattr(self.agent, "candidates_per_round", 18),
                    remaining_budget,
                )
                optimized = []
                signal_records = []
                if hasattr(self.agent, "optimizable_signal_records"):
                    signal_records = self.agent.optimizable_signal_records()
                if signal_records:
                    quality = getattr(self.agent, "quality_policy", {}) or {}
                    optimized = self.factory.optimize_signal_proposals(
                        signal_records,
                        bundle.get("operator_reference") or {},
                        max_candidates=min(4, candidate_cap),
                        excluded_expressions=self._known_expressions(),
                        min_sharpe=quality.get("promising_sharpe", 0.9),
                        min_fitness=quality.get("promising_fitness", 0.6),
                        min_turnover=quality.get("min_turnover", 0.01),
                        max_turnover=quality.get("max_turnover", 0.7),
                    )
                baseline = self.factory.assemble_proposals(
                    hypothesis,
                    bundle.get("fields") or [],
                    bundle.get("operator_reference") or {},
                    max_candidates=max(0, candidate_cap - len(optimized)),
                    excluded_expressions=self._known_expressions(),
                )
                proposals = optimized + baseline
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                if self._stop_on_terminal_error(session, "ASSEMBLE", exc):
                    break
                self._record_retry(session, "ASSEMBLE_ERROR", exc)
                self._save_session(session)
                self._bounded_sleep(self._retry_delay(idle, session), session["deadline"])
                continue
            payload = {
                "round_no": round_no,
                "epoch_label": bundle.get("epoch_label"),
                "factory_session_id": session["session_id"],
                "hypothesis": hypothesis,
                "proposals": proposals,
                "source": "ai_factory_template_adapter",
            }
            # One canonical proposals inbox is overwritten only when its
            # logical content changes.  It is not a per-round artifact.
            try:
                atomic_write_json_if_changed(self.proposals_path, payload)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                self._record_retry(session, "PROPOSALS_WRITE_ERROR", exc)
                self._save_session(session)
                self._bounded_sleep(self._retry_delay(idle, session), session["deadline"])
                continue
            if not proposals:
                session["probe_offset"] = probe_offset + 1
                session["last_action"] = "WAIT_NO_VALID_PROPOSAL"
                session["last_result"] = {"round_no": round_no, "proposals": 0}
                self._save_session(session)
                self._bounded_sleep(idle, session["deadline"])
                continue
            session["last_action"] = "RUN_PROPOSALS"
            session["probe_offset"] = 0
            session["simulations_reserved"] = (
                int(session.get("simulations_reserved", 0)) + len(proposals)
            )
            self._save_session(session)
            try:
                result = self._call(self.agent.run_proposals, self.proposals_path)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                if self._stop_on_terminal_error(session, "RUN_PROPOSALS", exc):
                    break
                # The proposal file and checkpoint were persisted before the
                # production call.  Keep the reservation and let the next
                # loop recover the same checkpoint; never create a replacement
                # POST after an ambiguous execution exception.
                self._record_retry(session, "RUN_PROPOSALS_ERROR", exc)
                self._save_session(session)
                self._bounded_sleep(self._retry_delay(idle, session), session["deadline"])
                continue
            session["retry_count"] = 0
            if self._unfinished_checkpoint():
                # The Agent durably handed off an unresolved batch. Keep its
                # reservation and round number; the next loop will recover
                # the same checkpoint instead of accounting it twice.
                session["last_action"] = "RUN_PROPOSALS_PENDING"
                self._save_session(session)
                continue
            accepted = self._accepted_count(len(proposals))
            # Preflight reservation is conservative.  Release only candidates
            # the canonical Agent explicitly rejected/skipped; accepted jobs
            # remain charged even when remote state is unresolved.
            session["simulations_reserved"] = max(
                0,
                int(session.get("simulations_reserved", 0)) - len(proposals) + accepted,
            )
            session["rounds_completed"] += 1
            session["last_action"] = "ROUND_COMPLETE"
            session["last_result"] = self._compact_result(round_no, result, len(proposals))
            self._save_session(session)

        if session["status"] == "RUNNING":
            session["status"] = "DEADLINE"
        session["finished_at"] = self._clock()
        self._save_session(session)
        return session

    @staticmethod
    def _checkpoint_round(path):
        match = re.search(r"round_(\d+)\.checkpoint\.json$", path)
        return int(match.group(1)) if match else None

    def _proposal_round(self):
        try:
            with open(self.proposals_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            value = payload.get("round_no") if isinstance(payload, dict) else None
            return int(value) if value is not None else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _orphaned_canonical_proposals(self, session):
        """Find a factory inbox left between reservation and checkpoint creation."""
        if session.get("last_action") not in {
            "RUN_PROPOSALS", "RECOVER_PROPOSALS",
        }:
            return []
        try:
            round_no = int(session.get("last_round"))
        except (TypeError, ValueError):
            return []
        if isinstance(session.get("last_result"), dict):
            try:
                if int(session["last_result"].get("round_no")) == round_no:
                    return []
            except (TypeError, ValueError):
                pass
        checkpoint = self._load_checkpoint_payload(round_no)
        if checkpoint and checkpoint.get("complete"):
            return []
        if checkpoint and not checkpoint.get("complete"):
            return []
        try:
            with open(self.proposals_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []
        if payload.get("factory_session_id") != session.get("session_id"):
            return []
        try:
            if int(payload.get("round_no")) != round_no:
                return []
        except (TypeError, ValueError):
            return []
        proposals = payload.get("proposals")
        return proposals if isinstance(proposals, list) and proposals else []

    def _load_checkpoint_payload(self, round_no):
        path = os.path.join(self.state_dir, f"round_{int(round_no)}.checkpoint.json")
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _accepted_count(self, proposal_count):
        stats = getattr(self.agent, "last_run_stats", {})
        accepted = stats.get("accepted", proposal_count) if isinstance(stats, dict) else proposal_count
        try:
            return max(0, min(proposal_count, int(accepted)))
        except (TypeError, ValueError):
            return proposal_count

    @staticmethod
    def _checkpoint_experiment_count(path):
        """Count checkpoint slots without materializing experiment objects."""
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            experiments = payload.get("experiments") if isinstance(payload, dict) else None
            return len(experiments) if isinstance(experiments, list) else 0
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return 0

    @staticmethod
    def _recovery_already_reserved(session, checkpoint_round):
        """Avoid double charging after a factory crash at a recovery boundary."""
        try:
            last_round = int(session.get("last_round"))
        except (TypeError, ValueError):
            last_round = None
        return (
            last_round == checkpoint_round
            and session.get("last_action") in {
                "RUN_PROPOSALS", "RUN_PROPOSALS_ERROR",
                "RECOVER_CHECKPOINT", "RECOVER_CHECKPOINT_ERROR",
                "RECOVER_PROPOSALS", "RECOVER_PROPOSALS_ERROR",
                "RECOVER_PROPOSALS_PENDING", "RUN_PROPOSALS_PENDING",
            }
        )

    def _known_expressions(self):
        """Return a bounded advisory prefilter for already seen expressions.

        The production Agent performs the authoritative streaming trajectory
        dedupe.  This small set only avoids obvious recent/memory duplicates
        before writing the canonical proposals inbox.
        """
        values = set()
        memory = getattr(self.agent, "memory", None)
        if memory is not None:
            values.update(
                canonical_expression(value)
                for value in (getattr(memory, "seen_expressions", set()) or set())
                if isinstance(value, (str, int)) and canonical_expression(value)
            )
        trajectory = getattr(self.agent, "trajectory", None)
        if trajectory is not None:
            for experiment in getattr(trajectory, "experiments", []) or []:
                expression = getattr(experiment, "expression", None)
                if isinstance(expression, (str, int)) and expression:
                    values.add(canonical_expression(expression))
        return values

    @staticmethod
    def _string_ids(values):
        """Normalize AI-authored dataset/id lists without inventing values."""
        if isinstance(values, (str, int)):
            values = [values]
        if not isinstance(values, (list, tuple, set)):
            return []
        result = []
        for value in values:
            if isinstance(value, dict):
                value = value.get("id") or value.get("name")
            if isinstance(value, (str, int)) and str(value).strip():
                item = str(value)
                if item not in result:
                    result.append(item)
        return result

    def _save_session(self, session):
        # A concurrent --factory-stop may replace the envelope between two
        # runner writes.  Preserve that control-plane bit for the same
        # session, while allowing a genuinely new session to start cleanly.
        current = self.read_session(self.state_dir)
        if (
            current
            and current.get("session_id") == session.get("session_id")
            and current.get("stop_requested")
        ):
            session["stop_requested"] = True
        atomic_write_json_if_changed(
            self.session_path, session, ignored_keys=("updated_at",)
        )

    def _load_session(self):
        session = self.read_session(self.state_dir)
        try:
            if not session:
                return None
            session["deadline"] = float(session["deadline"])
            session["rounds_completed"] = max(0, int(session.get("rounds_completed", 0)))
            session["simulations_reserved"] = max(
                0, int(session.get("simulations_reserved", 0))
            )
            session["simulation_cap"] = max(0, int(session.get("simulation_cap", 240)))
            if not isinstance(session.get("status"), str):
                return None
            return session
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass
        return None

    def _bounded_sleep(self, seconds, deadline):
        remaining = max(0.0, deadline - self._clock())
        if remaining > 0:
            self._sleep(min(seconds, remaining))

    def _call(self, function, *args):
        """Run agent work without turning every internal round into a report."""
        if not self.quiet:
            return function(*args)
        # ``StringIO`` retained every print from a potentially large round
        # until the call returned.  The factory is intentionally quiet, so a
        # sink is sufficient and keeps peak memory independent of log volume.
        with redirect_stdout(_DISCARD_STDOUT):
            return function(*args)

    @staticmethod
    def _retry_delay(base, session):
        """Bound repeated transient failures without busy-looping the API."""
        try:
            count = max(0, int(session.get("retry_count", 0)))
        except (TypeError, ValueError):
            count = 0
        return min(60.0, float(base) * (2 ** min(max(count - 1, 0), 6)))

    @staticmethod
    def _record_retry(session, action, exc):
        session["last_action"] = action
        session["retry_count"] = int(session.get("retry_count", 0)) + 1
        session["last_result"] = {
            "status": "RETRYING",
            "error_type": type(exc).__name__,
            "message": str(exc)[:200],
        }

    def _stop_on_terminal_error(self, session, action, exc):
        """Stop deterministic/safety errors instead of retrying all day."""
        error_name = type(exc).__name__
        terminal_names = {
            "WQBAuthError", "WQBSubmitUnknownError", "WQBRejectedError",
        }
        if not isinstance(exc, (ValueError, KeyError, TypeError)) and error_name not in terminal_names:
            return False
        session["status"] = "RECONCILE_REQUIRED"
        session["last_action"] = f"{action}_RECONCILE_REQUIRED"
        session["last_result"] = {
            "status": "RECONCILE_REQUIRED",
            "error_type": error_name,
            "message": str(exc)[:200],
        }
        self._save_session(session)
        return True

    def _unfinished_checkpoint(self):
        result = None
        result_round = None
        try:
            entries = os.scandir(self.state_dir)
        except OSError:
            return None
        with entries:
            for entry in entries:
                match = re.fullmatch(r"round_(\d+)\.checkpoint\.json", entry.name)
                if not match:
                    continue
                checkpoint_round = int(match.group(1))
                if result_round is not None and checkpoint_round >= result_round:
                    continue
                path = entry.path
                try:
                    stat = entry.stat()
                    signature = (stat.st_mtime_ns, stat.st_size)
                    if self._complete_checkpoint_signatures.get(entry.name) == signature:
                        continue
                    with open(path, encoding="utf-8") as handle:
                        payload = json.load(handle)
                    if not isinstance(payload, dict) or not payload.get("complete", False):
                        result = path
                        result_round = checkpoint_round
                    else:
                        self._complete_checkpoint_signatures[entry.name] = signature
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    result = path
                    result_round = checkpoint_round
        if len(self._complete_checkpoint_signatures) > self.CHECKPOINT_CACHE_MAX:
            ordered = sorted(
                self._complete_checkpoint_signatures.items(),
                key=lambda item: self._checkpoint_round(item[0]) or -1,
            )
            self._complete_checkpoint_signatures = dict(
                ordered[-self.CHECKPOINT_CACHE_MAX:]
            )
        return result

    @staticmethod
    def _compact_result(round_no, result, proposal_count):
        if not isinstance(result, dict):
            return {"round_no": round_no, "proposals": proposal_count,
                    "result": "none" if result is None else type(result).__name__}
        return {
            "round_no": round_no,
            "proposals": proposal_count,
            "summary_round": result.get("round"),
            "verdicts": result.get("verdicts"),
            "best": (result.get("best") or {}).get("expression")
                    if isinstance(result.get("best"), dict) else None,
        }
