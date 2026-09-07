"""Reflection: classify results with a comprehensive quality gate, diagnose
FAILs, learn, update best, mark hypothesis outcomes, and generate next
experiments that carry the concrete fields/datasets.

Six metrics read from every real simulation (BRAIN definitions):

- Sharpe   = Avg. Annualized Returns / Annualized Std. Dev. of Returns
- Turnover = Value Traded / Value Held
- Fitness  = Sharpe * sqrt( Abs(Returns) / Max(Turnover, 0.125) )
- Returns  = annualized avg gain/loss (invested amount = half book size)
- Drawdown = largest reduction in PnL during the period (fraction)
- Margin   = PnL per dollar traded

The verdict is a comprehensive judgment: hard failures come from failed
submission checks, low Sharpe/Fitness, excessive turnover, non-positive
margin and too-deep drawdown; soft warnings (very low turnover, returns
sign mismatch) do not block SUCCESS on their own.
"""

import re

from .evidence import overlay_cached_checks
from .failures import (
    FailureKind,
    classify_experiment,
    is_research_relevant,
)
from .metrics import check_pass, checks_passed, normalized_metrics, score_of

# Failed-check names from BRAIN payloads -> diagnosis category.
CHECK_DIAGNOSIS = [
    (re.compile(r"sub[-_ ]?universe", re.I), "sub_universe"),
    (re.compile(r"self[-_ ]?correlation", re.I), "self_correlation"),
    (re.compile(r"concentration", re.I), "weight_concentration"),
    (re.compile(r"turnover", re.I), "turnover"),
    (re.compile(r"syntax", re.I), "syntax"),
    (re.compile(r"expression", re.I), "expression_logic"),
    (re.compile(r"coverage|nan|data", re.I), "data_coverage"),
]


class Reflector:
    def __init__(
        self,
        memory,
        success_sharpe=1.0,
        promising_sharpe=0.7,
        promising_fitness=0.5,
        success_fitness=1.0,
        min_turnover=0.01,
        max_turnover=1.5,
        max_drawdown=0.5,
        self_correlation_limit=0.5,
        evidence_cache=None,
    ):
        self.memory = memory
        self.success_sharpe = success_sharpe
        self.promising_sharpe = promising_sharpe
        self.promising_fitness = promising_fitness
        self.success_fitness = success_fitness
        self.min_turnover = min_turnover
        self.max_turnover = max_turnover
        self.max_drawdown = max_drawdown
        self.self_correlation_limit = self_correlation_limit
        # 平台证据缓存侧车（alpha_id -> 已结算 checks）；见 wqb_agent/evidence.py。
        self.evidence_cache = evidence_cache or {}

    def reflect(self, round_no, hypothesis, experiments):
        results = []
        for exp in experiments:
            verdict = self._classify(exp)
            results.append({"experiment": exp, "verdict": verdict})
            self._learn(round_no, hypothesis, exp, verdict)

        old_best_id = (self.memory.current_best or {}).get("id")
        best = self._update_best(results)
        self._update_lineages(round_no, results)
        self._generate_next(round_no, hypothesis, results)
        self._mark_hypothesis_outcome(hypothesis, results)
        self._recap(round_no, hypothesis, results, best, old_best_id)
        self.memory.expire_short_term(now_round=round_no)
        self.memory.updated_round = round_no
        self.memory.compress()
        self.memory.save()

        return self._summary(round_no, hypothesis, results, best)

    # ----------------------------------------------------------- classify

    def _classify(self, exp):
        if exp.status in ("SKIPPED_STALE", "SKIPPED_UNKNOWN"):
            return {
                "label": "SKIPPED",
                "reason": "execution skipped after repeated read-only reconciliation; no research conclusion",
                "diagnosis": ["reconciliation_stale"],
                "kind": None,
                "notes": [],
            }
        if exp.status == "UNKNOWN":
            # 本地异常不证明 POST 未发生：先只读对账，不当作方向结论。
            return {
                "label": "FAIL",
                "reason": "UNKNOWN: requires read-only reconciliation before retry",
                "diagnosis": ["unknown"],
                "kind": None,
                "notes": [],
            }
        if exp.status == "FAILED":
            kind = classify_experiment(exp)
            return {
                "label": "FAIL",
                "reason": self._diagnose_error(exp),
                "diagnosis": ["runtime"],
                "kind": kind,
                "notes": [],
            }
        metrics = exp.metrics or {}
        # 平台证据缓存叠加：SELF_CORRELATION 等异步检查在模拟完成时通常仍为
        # PENDING；缓存侧车提供平台侧已结算结果，仅用于本判定视图。
        cached = (self.evidence_cache or {}).get(getattr(exp, "alpha_id", None))
        if cached:
            metrics = overlay_cached_checks(
                metrics, cached, self.self_correlation_limit
            )
        metrics = normalized_metrics(metrics)
        required_metrics = ("sharpe", "fitness", "turnover", "returns", "drawdown", "margin")
        checks = metrics.get("checks")
        malformed_checks = not (
            isinstance(checks, list) and checks
            and all(isinstance(check, dict) and check.get("name")
                    and check_pass(check) is not None for check in checks)
        )
        missing_metrics = [name for name in required_metrics if metrics.get(name) is None]
        if malformed_checks or missing_metrics:
            return {
                "label": "RECONCILE",
                "reason": "mandatory checks/metrics incomplete; promotion and research decision deferred",
                "diagnosis": (
                    (["missing_checks"] if malformed_checks else [])
                    + (["missing_metrics"] if missing_metrics else [])
                ),
                "kind": None,
                "notes": [],
            }
        sharpe = metrics.get("sharpe")
        if sharpe is None:
            return {"label": "FAIL", "reason": "missing sharpe metric",
                    "diagnosis": ["missing_metrics"], "kind": None, "notes": []}

        # 仅权重集中/极窄持仓才是噪声陷阱。健康检查还会报告
        # LOW_SUB_UNIVERSE_SHARPE；把后者误标为 weight_concentration 会污染
        # 后续的失败模式学习，因此它应继续走真实 checks 的诊断路径。
        health = getattr(exp, "health", None)
        health_reasons = (health or {}).get("reasons") or []
        concentrated = any(
            "concentrated_weight" in str(reason).lower()
            or "longcount=" in str(reason).lower()
            or "shortcount=" in str(reason).lower()
            for reason in health_reasons
        )
        if concentrated:
            return {
                "label": "FAIL",
                "reason": "NOISE_TRAP: " + "; ".join(health_reasons),
                "diagnosis": ["weight_concentration"],
                "notes": [],
            }

        fitness = metrics.get("fitness")
        if (sharpe is not None and sharpe > 3) or (fitness is not None and fitness > 8):
            return {
                "label": "SUSPICIOUS_HIGH_SIGNAL",
                "reason": "SUSPICIOUS_HIGH_SIGNAL: requires independent perturbation validation",
                "diagnosis": ["high_signal_unvalidated"],
                "notes": [],
            }

        hard, soft = self._quality_gate(metrics)
        if not hard:
            reason = " or ".join(soft) or "passed comprehensive gate"
            return {"label": "SUCCESS", "reason": reason,
                    "diagnosis": [], "notes": soft}

        reason = " or ".join(hard + soft) or "below quality gate"
        # 2026-08-22 用户政策：sharpe>promising_sharpe OR fitness>promising_fitness
        # 且换手在允许范围内（hard 中未含换手问题时）即视为有信号，可进入优化。
        signal = (sharpe is not None and sharpe > self.promising_sharpe) or (
            fitness is not None and fitness > self.promising_fitness
        )
        turnover_ok = not any("turnover" in h for h in hard)
        if signal and turnover_ok:
            return {"label": "PROMISING", "reason": reason,
                    "diagnosis": self._diagnosis_from(hard + soft), "notes": soft}
        return {"label": "FAIL", "reason": reason,
                "diagnosis": self._diagnosis_from(hard + soft), "notes": soft}

    def _quality_gate(self, metrics):
        """Comprehensive judgment over all six metrics + submission checks.
        Returns (hard_issues, soft_notes)."""
        metrics = normalized_metrics(metrics)
        hard, soft = [], []
        checks = metrics.get("checks") or []
        failed_checks = [c.get("name") for c in checks if check_pass(c) is not True]
        if failed_checks:
            hard.append(f"checks failed: {failed_checks}")
        elif not checks:
            hard.append("submission checks missing/unverified")

        sharpe = metrics.get("sharpe")
        fitness = metrics.get("fitness")
        turnover = metrics.get("turnover")
        margin = metrics.get("margin")
        returns = metrics.get("returns")
        drawdown = metrics.get("drawdown")

        missing = [
            name for name, value in (
                ("sharpe", sharpe), ("fitness", fitness),
                ("turnover", turnover), ("returns", returns),
                ("drawdown", drawdown), ("margin", margin),
            )
            if value is None
        ]
        if missing:
            hard.append(f"missing metrics: {missing}")

        if sharpe is not None and sharpe < self.success_sharpe:
            hard.append(f"sharpe {sharpe:.2f} < {self.success_sharpe}")
        if fitness is not None and fitness < self.success_fitness:
            hard.append(f"fitness {fitness:.2f} < {self.success_fitness}")
        if turnover is not None:
            if turnover > self.max_turnover:
                hard.append(f"turnover {turnover:.2f} too high")
            elif turnover < self.min_turnover:
                soft.append(f"turnover {turnover:.3f} very low (thin book)")
        if margin is not None and margin <= 0:
            hard.append(f"margin {margin:.4f} <= 0 (loses per dollar traded)")
        if drawdown is not None and drawdown > self.max_drawdown:
            hard.append(f"drawdown {drawdown:.2f} too deep")
        if returns is not None and sharpe is not None and (returns > 0) != (sharpe > 0):
            soft.append("returns/sharpe sign mismatch")

        return hard, soft

    @staticmethod
    def _diagnosis_from(issues):
        diagnosis = []
        for issue in issues:
            if "missing metrics" in issue:
                diagnosis.append("missing_metrics")
            elif "submission checks missing" in issue:
                diagnosis.append("missing_checks")
            elif "sharpe" in issue:
                diagnosis.append("sharpe")
            elif "fitness" in issue:
                diagnosis.append("fitness")
            elif "turnover" in issue:
                diagnosis.append("turnover")
            elif "margin" in issue:
                diagnosis.append("margin")
            elif "drawdown" in issue:
                diagnosis.append("drawdown")
            elif "checks" in issue:
                for check in re.findall(r"\[([^\]]+)\]", issue):
                    cat = Reflector._categorize_check(check)
                    if cat and cat not in diagnosis:
                        diagnosis.append(cat)
                if not diagnosis:
                    diagnosis.append("checks_failed")
            elif "returns" in issue:
                diagnosis.append("returns_sign")
        return diagnosis or ["no_signal"]

    @staticmethod
    def _categorize_check(name):
        for pattern, category in CHECK_DIAGNOSIS:
            if pattern.search(name or ""):
                return category
        return None

    def _diagnose_error(self, exp):
        error = exp.error or ""
        if "Simulation rejected" in error or "422" in error or "400" in error:
            return f"syntax/settings rejection: {error[:120]}"
        if "timed out" in error.lower():
            return "polling timed out"
        if "PLATFORM_ERROR" in error or "500" in error:
            return f"platform error (not an alpha-quality issue): {error[:120]}"
        return f"runtime error: {error[:120]}"

    # -------------------------------------------------------------- learn

    def _learn(self, round_no, hypothesis, exp, verdict):
        if exp.status in ("SKIPPED_STALE", "SKIPPED_UNKNOWN"):
            return
        if exp.status == "UNKNOWN":
            # 不确定结果不进入 lessons/avoid（不是方向结论），先入短期
            # 记忆待对账：只读核对后再决定晋升长期或移入垃圾。
            self.memory.forget_expression(exp.expression)
            self.memory.add_short_term(
                "pending",
                f"UNKNOWN experiment needs read-only reconciliation: "
                f"{exp.expression[:120]} (error={str(exp.error)[:80]})",
                round_no,
                evidence=1,
                detail="run reconciliation, then confirm_pending(verdict)",
            )
            return
        if verdict["label"] == "RECONCILE":
            self.memory.add_short_term(
                "pending",
                f"DONE experiment has incomplete mandatory evidence: {exp.expression[:120]}",
                round_no,
                evidence=1,
                detail="reconcile checks/metrics before any research decision",
            )
            return
        if exp.status == "FAILED":
            kind = classify_experiment(exp)
            if kind is None or not is_research_relevant(kind):
                # 系统级失败（auth/rate-limit/timeout/infra）或 UNKNOWN：
                # 不携带方向结论，禁止写入 avoid（避免污染研究记忆）。
                self.memory.forget_expression(exp.expression)
                self.memory.add_short_term(
                    "observation",
                    f"System-level failure (kind={kind}) not learned: "
                    f"{exp.expression[:80]} error={str(exp.error)[:80]}",
                    round_no,
                    evidence=1,
                    detail="environment issue, no direction signal",
                )
                return
            self.memory.add_avoid(
                self._direction_key(exp),
                self._diagnose_error(exp),
                round_no,
            )
            return

        metrics = normalized_metrics(exp.metrics or {})
        fields = exp.fields_used
        field_label = ",".join(fields) if fields else "?"

        if verdict["label"] in ("SUCCESS", "PROMISING", "SUSPICIOUS_HIGH_SIGNAL"):
            # A single backtest is an observation, never a durable lesson or
            # a new champion. The concrete platform id makes it auditable.
            self.memory.add_short_term(
                "observation",
                f"{verdict['label']} alpha={exp.alpha_id or exp.id} fields=[{field_label}] "
                f"sharpe={metrics.get('sharpe')} fitness={metrics.get('fitness')}; "
                f"needs independent lineage confirmation before promotion.",
                round_no,
                evidence=1,
                detail={
                    "experiment_id": exp.id,
                    "alpha_id": exp.alpha_id,
                    "lineage": exp.hypothesis_id,
                },
            )
            if verdict["label"] == "SUSPICIOUS_HIGH_SIGNAL":
                self.memory.add_next(
                    f"Validate suspicious high signal with one window perturbation and one field swap: {exp.expression}",
                    priority=6,
                    source=round_no,
                    round_no=round_no,
                    fields=fields,
                    datasets=exp.datasets,
                )
            elif verdict["label"] == "PROMISING":
                self.memory.add_next(
                    f"Test one alternative explanation for [{field_label}] (not a parameter sweep).",
                    priority=4,
                    source=round_no,
                    round_no=round_no,
                    fields=fields,
                    datasets=exp.datasets,
                )
        else:
            self.memory.add_avoid(
                self._direction_key(exp),
                f"sharpe={metrics.get('sharpe')}, fitness={metrics.get('fitness')}, "
                f"turnover={metrics.get('turnover')}, drawdown={metrics.get('drawdown')}, "
                f"margin={metrics.get('margin')}; diagnosis={verdict.get('diagnosis')}",
                round_no,
            )

        turnover = metrics.get("turnover")
        if turnover is not None and turnover > self.max_turnover:
            self.memory.add_short_term(
                "observation",
                f"alpha={exp.alpha_id or exp.id} turnover={turnover:.2f} exceeds quality gate on [{field_label}]",
                round_no,
                evidence=1,
                detail={"experiment_id": exp.id, "lineage": exp.hypothesis_id},
            )

    @staticmethod
    def _direction_key(exp):
        return exp.expression[:80]

    # --------------------------------------------------------------- best

    @staticmethod
    def _exp_score(exp):
        """实验统一评分（复用 metrics.score_of，只算有指标的实验）。"""
        return score_of((exp.metrics or {}) or None)

    def _update_best(self, results):
        done = [
            r for r in results
            if r["experiment"].metrics
            and r["verdict"]["label"] == "SUCCESS"
            and getattr(r["experiment"], "validation_status", None) == "STABLE"
        ]
        if not done:
            current = self.memory.current_best
            metrics = (current or {}).get("metrics") or {}
            if checks_passed(metrics) is True and (current or {}).get("validation_status") == "STABLE":
                return current
            return None
        best_exp = max(done, key=lambda r: self._exp_score(r["experiment"]))["experiment"]
        best_score = self._exp_score(best_exp)
        current_score = None
        if self.memory.current_best and self.memory.current_best.get("metrics"):
            current_score = score_of(self.memory.current_best["metrics"])
        if current_score is None or best_score > current_score:
            self.memory.set_current_best(best_exp)
            return best_exp.to_dict()
        return self.memory.current_best

    # --------------------------------------------------------------- next

    def _update_lineages(self, round_no, results):
        """Convert resolved BRAIN evidence into bounded budget decisions."""
        for result in results:
            exp = result["experiment"]
            if exp.status != "DONE" or result["verdict"]["label"] == "RECONCILE":
                continue
            lineage_id = getattr(exp, "lineage_id", None) or exp.hypothesis_id
            label = result["verdict"]["label"]
            # 2026-08-22 用户政策：两次无增益 STOP / 三次无增益 KILL 的防过拟合
            # 纪律只适用于已达可提交标准（过硬质量门 SUCCESS）的候选；有信号但
            # 未达标（PROMISING）或未定论的谱系不因次数关闭，换优化变量类别继续。
            decision = self.memory.record_lineage_result(
                lineage_id, self._exp_score(exp), label, round_no,
                counts_toward_stop=(label == "SUCCESS"),
            )
            if decision in ("STOP", "KILL"):
                self.memory.add_short_term(
                    "observation",
                    f"{decision} lineage={lineage_id}: repeated resolved experiments "
                    "produced no material information gain.",
                    round_no,
                    evidence=1,
                    detail={"experiment_id": exp.id, "lineage": lineage_id},
                )

    def _generate_next(self, round_no, hypothesis, results):
        # A one-off pass is observation-only, so it cannot schedule an
        # automatic deepening branch. Promotion needs independent evidence.
        successes = []
        promising = [r for r in results if r["verdict"]["label"] == "PROMISING"]
        failed_all = all(r["verdict"]["label"] == "FAIL" for r in results)

        if successes:
            for r in successes[:2]:
                exp = r["experiment"]
                self.memory.add_next(
                    f"Deepen successful expression: {exp.expression}",
                    priority=5,
                    source=round_no,
                    round_no=round_no,
                    fields=exp.fields_used,
                    datasets=exp.datasets,
                )
        if promising:
            for r in promising[:2]:
                exp = r["experiment"]
                self.memory.add_next(
                    f"Improve promising expression: {exp.expression} "
                    f"(fixing {r['verdict'].get('diagnosis')})",
                    priority=4,
                    source=round_no,
                    round_no=round_no,
                    fields=exp.fields_used,
                    datasets=exp.datasets,
                )
        if failed_all:
            # UNKNOWN experiments exist -> not a clean all-fail round.
            if any(r["experiment"].status == "UNKNOWN" for r in results):
                return
            # 系统级失败（auth/rate-limit/timeout/infra）不证明方向失败，
            # 只有全部是研究级失败才触发方向切换。
            research_fails = [
                r for r in results
                if classify_experiment(r["experiment"]) is None
                or is_research_relevant(classify_experiment(r["experiment"]))
            ]
            if len(research_fails) != len(results):
                return
            tags = hypothesis.get("tags", [])
            # No fields/datasets on purpose: a "switch direction" idea must
            # not be picked as an actionable field-bearing next idea.
            self.memory.add_next(
                f"Switch research direction away from tags {tags}",
                priority=3,
                source=round_no,
                round_no=round_no,
            )

    def _mark_hypothesis_outcome(self, hypothesis, results):
        hyp_id = hypothesis.get("id")
        if not hyp_id:
            return
        if (any(r["experiment"].status == "UNKNOWN" for r in results)
                or any(r["verdict"]["label"] == "RECONCILE" for r in results)):
            # 有不确定结果：保持 active，先对账再定论。
            self.memory.mark_hypothesis(hyp_id, "active", hypothesis.get("_round", 0))
            return
        labels = [r["verdict"]["label"] for r in results]
        if "SUCCESS" in labels:
            verdict = "success"
        elif "PROMISING" in labels:
            verdict = "promising"
        else:
            verdict = "failed"
        self.memory.mark_hypothesis(hyp_id, verdict, hypothesis.get("_round", 0))

    # ------------------------------------------------------------ recap

    def _recap(self, round_no, hypothesis, results, best, old_best_id):
        """Write a short-term round recap — the working memory the model
        reads next round before deciding what to explore. Never a
        long-term claim: conclusions live in lessons/avoid; this is the
        ephemeral 'what just happened' view."""
        labels = {}
        for r in results:
            labels[r["verdict"]["label"]] = labels.get(r["verdict"]["label"], 0) + 1
        parts = [
            f"round {round_no}",
            f"hypothesis={hypothesis.get('statement', '')[:80]}",
            "verdicts=" + (",".join(f"{k}:{v}" for k, v in sorted(labels.items())) or "none"),
        ]
        top = None
        for r in results:
            m = r["experiment"].metrics or {}
            if not m:
                continue
            score = m.get("fitness") or m.get("sharpe") or -1
            if top is None or score > top[1]:
                top = (r["experiment"], score, m)
        if top:
            exp, _score, m = top
            parts.append(
                f"top sharpe={m.get('sharpe')} fitness={m.get('fitness')} "
                f"expr={exp.expression[:60]}"
            )
        if best and best.get("id") != old_best_id:
            parts.append("NEW BEST")
        self.memory.add_short_term("recap", " | ".join(parts), round_no)

    # ------------------------------------------------------------ summary

    def _summary(self, round_no, hypothesis, results, best):
        labels = {}
        for r in results:
            labels[r["verdict"]["label"]] = labels.get(r["verdict"]["label"], 0) + 1
        return {
            "round": round_no,
            "hypothesis": hypothesis.get("statement", ""),
            "experiment_count": len(results),
            "verdicts": labels,
            "best": (
                {
                    "expression": best["expression"],
                    "sharpe": (best.get("metrics") or {}).get("sharpe"),
                    "fitness": (best.get("metrics") or {}).get("fitness"),
                    "drawdown": (best.get("metrics") or {}).get("drawdown"),
                }
                if best
                else None
            ),
        }
