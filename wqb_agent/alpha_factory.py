"""Template-first Alpha candidate factory.

This is a proposal-construction layer only.  It does not call BRAIN, write
research state, or submit simulations.  A template describes the structural
shape of an Alpha; a field bundle supplies the slots.  The resulting metadata
keeps the skeleton visible to the later proposal and diversity gates.
"""

from dataclasses import dataclass
import hashlib
import json

from .diversity import extract_fields
from .expression import analyze_expression, canonical_expression


@dataclass(frozen=True)
class AlphaTemplate:
    """One bounded, inspectable expression skeleton."""

    template_id: str
    family: str
    expression: str
    required_slots: tuple = ("p",)
    stage_path: str = "L0:raw -> L1:cross_sectional -> L2:none"
    rationale: str = ""
    economic: bool = False

    @property
    def operator_count(self):
        """Count function-style operators in the skeleton."""
        return len(analyze_expression(self.expression).operators)

    @property
    def fingerprint(self):
        payload = json.dumps(
            {
                "family": self.family,
                "expression": self.expression,
                "required_slots": self.required_slots,
                "stage_path": self.stage_path,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def catalog_entry(self):
        reversal = "reversal" in self.family or "reversal" in self.rationale.lower()
        return {
            "template_id": self.template_id,
            "family": self.family,
            "expression": self.expression,
            "required_slots": list(self.required_slots),
            "stage_path": self.stage_path,
            "fingerprint": self.fingerprint,
            "source": "newwqb_builtin",
            "operator_count": self.operator_count,
            "economic": self.economic,
            "economic_mechanism": self.rationale,
            "direction": "reversal" if reversal else "long",
            "direction_transform": {
                "applied": reversal,
                "reason": (
                    "将高位/异常信号映射为反转方向。" if reversal
                    else "保持字段经济含义的正向预测，不做符号翻转。"
                ),
            },
            "expected_horizon": "由 hypothesis 与字段频率共同确定",
            "falsification": "独立样本、健康或平台 checks 不能支持机制时停止该模板。",
        }


DEFAULT_TEMPLATES = (
    AlphaTemplate(
        "rank_level", "cross_sectional_rank", "rank({p})",
        rationale="横截面排序，作为字段机制的最小基线。",
    ),
    AlphaTemplate(
        "zscore_level", "cross_sectional_standardize", "zscore({p})",
        rationale="横截面标准化，检验信号强度而非绝对尺度。",
    ),
    AlphaTemplate(
        "reversal_zscore_20", "reversal", "-rank(ts_zscore({p}, 20))",
        stage_path="L0:raw -> L1:ts_zscore -> L2:rank",
        rationale="检验短期异常值的反转机制。",
    ),
    AlphaTemplate(
        "momentum_mean_20", "momentum", "rank(ts_mean({p}, 20))",
        stage_path="L0:raw -> L1:ts_mean -> L2:rank",
        rationale="检验慢化后的持续性机制。",
    ),
    AlphaTemplate(
        "change_delta_5", "change", "rank(ts_delta({p}, 5))",
        stage_path="L0:raw -> L1:ts_delta -> L2:rank",
        rationale="检验字段变化而非水平本身。",
    ),
    AlphaTemplate(
        "group_neutralized_rank", "group_neutralized", "group_neutralize(rank({p}), {g})",
        stage_path="L0:raw -> L1:rank -> L2:group_neutralize",
        rationale="检验去除组别暴露后的增量信息。",
    ),
    AlphaTemplate(
        "spread_rank", "relationship_spread", "rank({p} - {s})",
        required_slots=("p", "s"),
        stage_path="L0:spread -> L1:rank -> L2:none",
        rationale="仅作为语义互补字段审阅后的差分构造。",
    ),
    AlphaTemplate(
        "vector_mean_rank", "vector_aggregation", "rank(vec_avg({p}))",
        stage_path="L0:VECTOR -> L1:vec_avg(MATRIX) -> L2:rank",
        rationale="先把真实 VECTOR 字段聚合为 MATRIX，再检验其横截面排序信息。",
    ),
)


# These are deliberately bounded economic mechanisms, not a Cartesian product
# of fields, windows, and operators.  Every new template uses 3-8 distinct
# function operators and exposes the mechanism in its rationale.  The
# proposal contract still validates fields, types, operator evidence, and
# lineage before any Simulation is submitted.
ECONOMIC_TEMPLATES = (
    AlphaTemplate(
        "quality_smooth_change", "quality_change",
        "rank(ts_decay_linear(ts_delta({p}, 5), 10))",
        stage_path="L0:raw -> L1:change -> L2:decay -> L3:rank",
        rationale="平滑盈利或质量指标的变化，检验信息持续性而非单日跳变。",
        economic=True,
    ),
    AlphaTemplate(
        "reversal_vol_adjusted", "risk_adjusted_reversal",
        "rank(divide(reverse(ts_delta({p}, 5)), add(ts_std_dev({p}, 20), 0.001)))",
        stage_path="L0:raw -> L1:delta/reversal -> L2:volatility adjustment -> L3:rank",
        rationale="把短期反转幅度按自身波动率调整，区分异常变化与正常噪声。",
        economic=True,
    ),
    AlphaTemplate(
        "persistent_level", "persistent_level",
        "rank(ts_zscore(ts_mean({p}, 20), 60))",
        stage_path="L0:raw -> L1:mean -> L2:longer-horizon zscore -> L3:rank",
        rationale="检验平滑后的相对高低是否具有持续性信息。",
        economic=True,
    ),
    AlphaTemplate(
        "downside_volatility", "downside_risk",
        "reverse(rank(ts_std_dev(ts_delta({p}, 5), 20)))",
        stage_path="L0:raw -> L1:change -> L2:volatility -> L3:rank/reversal",
        rationale="高变化波动代表不稳定风险，检验风险暴露与未来收益的反向关系。",
        economic=True,
    ),
    AlphaTemplate(
        "missing_resilient_change", "data_resilient_change",
        "rank(ts_delta(ts_backfill({p}, 20), 5))",
        stage_path="L0:raw -> L1:backfill -> L2:change -> L3:rank",
        rationale="在受控回看窗口内处理缺失后检验信息修正，避免覆盖率造成假信号。",
        economic=True,
    ),
    AlphaTemplate(
        "robust_cross_section", "robust_cross_section",
        "normalize(winsorize(rank({p}), 4), true, 0.0)",
        stage_path="L0:raw -> L1:rank -> L2:winsorize -> L3:normalize",
        rationale="先降低极端值影响，再去除横截面整体水平，检验稳健相对信号。",
        economic=True,
    ),
    AlphaTemplate(
        "distributional_change", "distributional_change",
        "quantile(rank(ts_delta({p}, 5)), gaussian, 1.0)",
        stage_path="L0:raw -> L1:change -> L2:rank -> L3:quantile",
        rationale="将变化信号映射到平滑分布，检验尾部排序之外的横截面信息。",
        economic=True,
    ),
    AlphaTemplate(
        "turnover_controlled_change", "turnover_control",
        "hump(rank(ts_delta({p}, 5)), 0.01)",
        stage_path="L0:raw -> L1:change -> L2:rank -> L3:hump",
        rationale="对变化信号限制日间跳动，检验降低换手后的净经济价值。",
        economic=True,
    ),
    AlphaTemplate(
        "event_triggered_signal", "event_trigger",
        "trade_when(ts_rank({p}, 20) > 0.8, rank(ts_delta({p}, 5)), ts_rank({p}, 20) < 0.2)",
        stage_path="L0:raw -> L1:ts_rank regime -> L2:event trigger -> L3:rank",
        rationale="只在历史极端区间触发交易，检验事件条件下的延续或反转。",
        economic=True,
    ),
    AlphaTemplate(
        "group_relative_change", "group_relative_change",
        "group_neutralize(rank(ts_delta({p}, 20)), {g})",
        stage_path="L0:raw -> L1:change -> L2:rank -> L3:group neutralize",
        rationale="剔除行业或板块共同变化，检验组内相对修正是否有增量信息。",
        economic=True,
    ),
    AlphaTemplate(
        "group_relative_extreme", "group_relative_extreme",
        "group_zscore(rank(ts_zscore({p}, 20)), {g})",
        stage_path="L0:raw -> L1:time-series zscore -> L2:group zscore",
        rationale="比较同组内相对于自身历史的异常程度，检验组内异质性。",
        economic=True,
    ),
    AlphaTemplate(
        "group_filled_rank", "group_data_repair",
        "group_rank(rank(group_backfill({p}, {g}, 20, 4)), {g})",
        stage_path="L0:raw -> L1:group backfill -> L2:group rank",
        rationale="用组内历史信息处理缺失，再检验组内相对位置，区分覆盖率与信号。",
        economic=True,
    ),
    AlphaTemplate(
        "vector_persistent_signal", "vector_persistence",
        "rank(ts_zscore(ts_mean(vec_avg({p}), 20), 60))",
        stage_path="L0:VECTOR -> L1:vec_avg -> L2:mean -> L3:zscore -> L4:rank",
        rationale="将真实 VECTOR 聚合后检验平滑、长期相对异常信号。",
        economic=True,
    ),
    AlphaTemplate(
        "vector_change_signal", "vector_change",
        "rank(ts_delta(ts_decay_linear(vec_sum({p}), 5), 5))",
        stage_path="L0:VECTOR -> L1:vec_sum -> L2:decay -> L3:delta -> L4:rank",
        rationale="检验向量总量的平滑变化是否代表集体信息更新。",
        economic=True,
    ),
    AlphaTemplate(
        "relative_spread_change", "relative_spread_change",
        "rank(ts_delta(subtract({p}, {s}), 5))",
        required_slots=("p", "s"),
        stage_path="L0:two fields -> L1:spread -> L2:delta -> L3:rank",
        rationale="只有语义互补字段才允许构造差值，检验相对变化而非单字段水平。",
        economic=True,
    ),
    AlphaTemplate(
        "relative_ratio_extreme", "relative_ratio",
        "rank(ts_zscore(divide({p}, add(abs({s}), 0.001)), 20))",
        required_slots=("p", "s"),
        stage_path="L0:two fields -> L1:safe ratio -> L2:time-series zscore -> L3:rank",
        rationale="用安全分母构造经济比例，再检验比例异常，避免无保护除零。",
        economic=True,
    ),
    AlphaTemplate(
        "relative_covariance", "relative_covariance",
        "rank(ts_zscore(ts_covariance({p}, {s}, 20), 60))",
        required_slots=("p", "s"),
        stage_path="L0:two fields -> L1:covariance -> L2:long-horizon zscore -> L3:rank",
        rationale="检验两个经济量的共同变化强度是否具有相对异常信息。",
        economic=True,
    ),
    AlphaTemplate(
        "relative_correlation_regime", "relative_correlation",
        "rank(ts_zscore(ts_corr({p}, {s}, 20), 60))",
        required_slots=("p", "s"),
        stage_path="L0:two fields -> L1:correlation -> L2:regime zscore -> L3:rank",
        rationale="检验两类互补信息同步程度的变化，而非简单堆叠字段。",
        economic=True,
    ),
    AlphaTemplate(
        "group_centered_level", "group_centered_level",
        "group_scale(group_mean(ts_zscore({p}, 20), 1, {g}), {g})",
        stage_path="L0:raw -> L1:ts zscore -> L2:group mean -> L3:group scale",
        rationale="先比较字段相对自身历史的位置，再用组内中心和尺度衡量共同偏离。",
        economic=True,
    ),
    AlphaTemplate(
        "extreme_location_reversal", "extreme_location",
        "reverse(rank(ts_arg_max(ts_zscore({p}, 20), 60)))",
        stage_path="L0:raw -> L1:ts zscore -> L2:arg max -> L3:rank/reversal",
        rationale="识别指标处在历史极端高位的资产，检验极端状态后的均值回归。",
        economic=True,
    ),
    AlphaTemplate(
        "extreme_low_continuation", "extreme_low",
        "rank(ts_arg_min(ts_zscore({p}, 20), 60))",
        stage_path="L0:raw -> L1:ts zscore -> L2:arg min -> L3:rank",
        rationale="识别长期低位但正在改善的指标，检验低位修复的持续性。",
        economic=True,
    ),
    AlphaTemplate(
        "innovation_surprise", "innovation_surprise",
        "rank(ts_zscore(ts_av_diff({p}, 20), 60))",
        stage_path="L0:raw -> L1:average deviation -> L2:long zscore -> L3:rank",
        rationale="提取当前值相对近期平均的创新程度，区分水平与新信息。",
        economic=True,
    ),
    AlphaTemplate(
        "delayed_confirmation", "delayed_confirmation",
        "rank(ts_zscore(ts_delta(ts_delay({p}, 5), 5), 60))",
        stage_path="L0:raw -> L1:delay -> L2:delta -> L3:zscore -> L4:rank",
        rationale="用滞后信息构造确认信号，检验信息扩散而非同步反应。",
        economic=True,
    ),
    AlphaTemplate(
        "accumulated_change", "accumulated_change",
        "rank(ts_zscore(ts_sum(ts_delta({p}, 5), 20), 60))",
        stage_path="L0:raw -> L1:delta -> L2:sum -> L3:zscore -> L4:rank",
        rationale="累计多个短期变化，检验渐进式信息积累的经济含义。",
        economic=True,
    ),
    AlphaTemplate(
        "distribution_regime", "distribution_regime",
        "rank(ts_quantile(ts_zscore({p}, 20), 60, gaussian))",
        stage_path="L0:raw -> L1:ts zscore -> L2:ts quantile -> L3:rank",
        rationale="将当前相对水平放回历史分布，识别状态切换而非绝对水平。",
        economic=True,
    ),
    AlphaTemplate(
        "adaptive_scale_change", "adaptive_scale_change",
        "rank(ts_scale(ts_delta({p}, 5), 20))",
        stage_path="L0:raw -> L1:delta -> L2:ts scale -> L3:rank",
        rationale="按近期尺度标准化变化，比较不同波动环境下的冲击强度。",
        economic=True,
    ),
    AlphaTemplate(
        "trend_residual", "trend_residual",
        "rank(ts_regression(ts_delta({p}, 5), ts_step(1), 20, 0))",
        stage_path="L0:raw -> L1:delta -> L2:regression -> L3:rank",
        rationale="剥离时间趋势后的变化残差，检验非趋势性信息冲击。",
        economic=True,
    ),
    AlphaTemplate(
        "compounding_pressure", "compounding_pressure",
        "rank(ts_zscore(ts_product(add({p}, 1), 10), 60))",
        stage_path="L0:raw -> L1:additive shift -> L2:product -> L3:zscore -> L4:rank",
        rationale="将连续小幅变化视为复合效应，检验累积压力或改善是否被低估。",
        economic=True,
    ),
    AlphaTemplate(
        "data_quality_penalty", "data_quality_penalty",
        "reverse(rank(ts_zscore(ts_count_nans({p}, 20), 60)))",
        stage_path="L0:raw -> L1:missing count -> L2:zscore -> L3:rank/reversal",
        rationale="将近期缺失频率作为信息质量风险，检验数据可用性与收益的关系。",
        economic=True,
    ),
    AlphaTemplate(
        "stale_information_reversal", "stale_information",
        "reverse(rank(ts_zscore(days_from_last_change({p}), 60)))",
        stage_path="L0:raw -> L1:staleness -> L2:zscore -> L3:rank/reversal",
        rationale="识别长期不更新的陈旧信息，检验信息滞后与未来反转。",
        economic=True,
    ),
    AlphaTemplate(
        "last_update_surprise", "last_update_surprise",
        "rank(ts_zscore(last_diff_value({p}, 20), 60))",
        stage_path="L0:raw -> L1:last difference -> L2:zscore -> L3:rank",
        rationale="聚焦最近一次变化相对历史的异常程度，检验更新事件的增量信息。",
        economic=True,
    ),
)

MAX_TEMPLATE_FAMILY_PER_BATCH = 2


class AlphaTemplateRegistry:
    """Immutable-by-default registry for built-in template skeletons."""

    def __init__(self, templates=None):
        self._templates = {}
        source = (DEFAULT_TEMPLATES + ECONOMIC_TEMPLATES
                  if templates is None else templates)
        for template in source:
            self.register(template)

    def register(self, template):
        if not isinstance(template, AlphaTemplate):
            raise TypeError("template 必须是 AlphaTemplate")
        if template.template_id in self._templates:
            raise ValueError(f"重复 template_id: {template.template_id}")
        if template.economic and not 3 <= template.operator_count <= 8:
            raise ValueError(
                f"经济模板 {template.template_id} 算子数必须在 3-8："
                f"{template.operator_count}"
            )
        self._templates[template.template_id] = template

    def get(self, template_id):
        return self._templates.get(template_id)

    def catalog(self):
        return [
            self._templates[key].catalog_entry()
            for key in sorted(self._templates)
        ]

    def economic_templates(self):
        return [
            self._templates[key]
            for key in sorted(self._templates)
            if self._templates[key].economic
        ]

    def select(self, hypothesis=None):
        if hypothesis is None:
            hypothesis = {}
        if not isinstance(hypothesis, dict):
            return []
        explicit = hypothesis.get("template_ids") or []
        if isinstance(explicit, str):
            explicit = [explicit]
        elif not isinstance(explicit, (list, tuple)):
            return []
        if any(not isinstance(item, str) or not item.strip() for item in explicit):
            return []
        selected = [self.get(item) for item in explicit]
        if explicit and any(item is None for item in selected):
            # A partially valid list is still invalid: silently dropping an
            # unknown id would make the proposal run a different skeleton
            # from the one the caller requested.
            return []
        selected = [item for item in selected if item is not None]
        if selected:
            return selected
        if explicit:
            # Explicit template intent must fail closed; silently replacing a
            # typo with a default family makes an AI appear to make progress
            # while repeatedly testing the wrong structure.
            return []

        ref = hypothesis.get("template_ref") or {}
        if not isinstance(ref, dict):
            return []
        family = hypothesis.get("template_family") or ref.get("family")
        if not family:
            family = ref.get("template_skeleton_family")
        if ref and not family and (
            ref.get("catalog_id") or ref.get("skeleton_fingerprint")
        ):
            return []
        raw_tags = hypothesis.get("tags")
        raw_tags = raw_tags if isinstance(raw_tags, (list, tuple, set)) else []
        tags = {str(tag).lower() for tag in raw_tags}
        direction = str(hypothesis.get("direction") or "").lower()
        if family:
            matching = [t for t in self._templates.values() if t.family == family]
            # An explicit family is an exact request, not a preference.  Do
            # not fall through to direction/tag defaults when it is unknown.
            return matching
        if direction == "reversal" or tags & {"reversal", "contrarian"}:
            ids = {"reversal_zscore_20", "change_delta_5", "rank_level"}
        elif tags & {"relationship", "pair", "spread", "corr"}:
            ids = {"spread_rank", "zscore_level", "rank_level"}
        elif tags & {"momentum", "trend", "continuation"}:
            ids = {"momentum_mean_20", "change_delta_5", "rank_level"}
        else:
            ids = {"rank_level", "zscore_level", "group_neutralized_rank"}
        return [self._templates[key] for key in sorted(ids)]


class AlphaFactory:
    """Instantiate templates into non-submitting candidate records."""

    def __init__(self, neutralization="SUBINDUSTRY", registry=None):
        self.neutralization = str(neutralization or "SUBINDUSTRY").lower()
        self.registry = registry or AlphaTemplateRegistry()

    @staticmethod
    def requested(hypothesis):
        """Whether the caller explicitly opted into template-first mode."""
        if not isinstance(hypothesis, dict):
            return False
        return bool(
            hypothesis.get("template_ids")
            or hypothesis.get("template_family")
            or hypothesis.get("template_ref")
        )

    def generate(self, hypothesis, fields, count=6):
        """Fill a bounded template set from verified field slots.

        Field descriptions and type checks remain the responsibility of the
        normal proposal preflight; this function never guesses them.
        """
        if not isinstance(hypothesis, dict):
            return []
        try:
            limit = max(0, int(count))
        except (TypeError, ValueError):
            return []
        if limit <= 0 or not isinstance(fields, (list, tuple)) or not fields:
            return []
        normalized = []
        for field in fields:
            field_id = field.get("id") if isinstance(field, dict) else field
            if isinstance(field_id, (str, int)) and field_id and str(field_id) not in normalized:
                normalized.append(str(field_id))
        if not normalized:
            return []
        primary = normalized[0]
        secondary = normalized[1] if len(normalized) > 1 else None
        ref_input = hypothesis.get("template_ref") or {}
        candidates = []
        seen = set()
        for template in self.registry.select(hypothesis):
            if any(slot == "s" and not secondary for slot in template.required_slots):
                continue
            values = {"p": primary, "s": secondary, "g": self.neutralization}
            try:
                expression = template.expression.format(**values)
            except (KeyError, ValueError):
                continue
            identity = canonical_expression(expression)
            if identity in seen:
                continue
            seen.add(identity)
            ref = dict(ref_input)
            ref.setdefault("catalog_id", f"builtin:{template.template_id}")
            ref.setdefault("skeleton_fingerprint", template.fingerprint)
            ref.setdefault("lifecycle", "runnable")
            ref.setdefault("source", "newwqb_builtin")
            ref.setdefault("slot_name", "p")
            slot_values = {"p": primary, "g": self.neutralization}
            if secondary:
                slot_values["s"] = secondary
            candidates.append(
                {
                    "expression": expression,
                    "rationale": template.rationale,
                    "mutation": f"template:{template.template_id}",
                    "parent": None,
                    "fields_used": extract_fields(expression, normalized),
                    "template_id": template.template_id,
                    "template_family": template.family,
                    "template_stage_path": template.stage_path,
                    "template_ref": ref,
                    "template_slots": slot_values,
                    "factory_version": "alpha-factory-v1",
                    "economic_mechanism": template.rationale,
                    "direction": (
                        "reversal" if "reversal" in template.family
                        or "reversal" in template.rationale.lower() else "long"
                    ),
                    "direction_transform": {
                        "applied": (
                            "reversal" in template.family
                            or "reversal" in template.rationale.lower()
                        ),
                        "reason": template.rationale,
                    },
                    "expected_horizon": "由 hypothesis 与字段频率共同确定",
                    "falsification": "独立样本、健康或平台 checks 不能支持机制时停止该模板。",
                }
            )
            if len(candidates) >= limit:
                break
        return candidates

    def catalog(self):
        return self.registry.catalog()

    def optimize_signal_proposals(self, parents, operator_reference,
                                   max_candidates=4, excluded_expressions=None,
                                   min_sharpe=0.9, min_fitness=0.6,
                                   min_turnover=0.01, max_turnover=0.7):
        """Create bounded CHILD proposals from already completed signals.

        This is autonomous optimization, not blind mutation: a parent must be
        DONE, have auditable discovery metadata, meet a configurable signal
        threshold, and stay within turnover bounds.  Each child changes one
        declared variable and still goes through the normal Agent preflight.
        """
        if not isinstance(parents, (list, tuple)) or not isinstance(operator_reference, dict):
            return []
        try:
            limit = max(0, int(max_candidates))
        except (TypeError, ValueError):
            return []
        excluded = {
            canonical_expression(value)
            for value in (excluded_expressions or [])
            if isinstance(value, str) and value.strip()
        }
        allowed = {str(value) for value in (operator_reference.get("operators") or [])}
        try:
            min_sharpe, min_fitness = float(min_sharpe), float(min_fitness)
            min_turnover, max_turnover = float(min_turnover), float(max_turnover)
        except (TypeError, ValueError):
            return []
        out = []
        seen_parents = set()
        for parent in parents:
            if len(out) >= limit or not isinstance(parent, dict):
                break
            if parent.get("status") != "DONE":
                continue
            # Automatic children previously performed generic smoothing and
            # window variants.  They are exactly the low-information tuning
            # loop this factory must stop producing.  A future child must be
            # supplied by the agent with a distinct economic mechanism and a
            # complete proposal contract instead of being invented here.
            if not isinstance(parent.get("child_economic_hypothesis"), dict):
                continue
            base = parent.get("expression")
            if not isinstance(base, str) or not base.strip():
                continue
            identity = canonical_expression(base)
            if identity in seen_parents or identity in excluded:
                continue
            seen_parents.add(identity)
            metrics = parent.get("metrics") or {}
            try:
                sharpe = float(metrics.get("sharpe"))
                fitness = float(metrics.get("fitness"))
                turnover = float(metrics.get("turnover"))
            except (TypeError, ValueError):
                continue
            if not ((sharpe >= min_sharpe or fitness >= min_fitness)
                    and min_turnover <= turnover <= max_turnover):
                continue
            if isinstance(parent.get("health"), dict) and not parent["health"].get("ok"):
                continue
            fields = parent.get("fields_used") or []
            datasets = parent.get("datasets") or []
            common = {
                "fields": list(fields),
                "datasets": list(datasets),
                "field_understanding": parent.get("field_understanding"),
                "field_analysis": parent.get("field_analysis"),
                "field_source": parent.get("field_source"),
                "field_hypothesis_basis": parent.get("field_hypothesis_basis"),
            }
            if (not fields or not datasets or not common["field_understanding"]
                    or not common["field_analysis"] or not common["field_source"]
                    or not common["field_hypothesis_basis"]):
                continue
            variants = (
                ("smoothing", f"hump({base}, 0.01)", "限制日间变化以降低换手"),
                ("operator_variant", f"rank(ts_decay_linear({base}, 10))",
                 "对已有信号增加近期加权平滑"),
            )
            for change_type, expression, rationale in variants:
                if len(out) >= limit:
                    break
                normalized = canonical_expression(expression)
                if normalized in excluded:
                    continue
                actual_ops = list(analyze_expression(expression).operators)
                if not set(actual_ops).issubset(allowed):
                    continue
                proposal = dict(common)
                proposal.update({
                    "expression": expression,
                    "operator_mapping": rationale,
                    "operator_evidence": {
                        "sha256": operator_reference.get("sha256"),
                        "operators": actual_ops,
                        "rationale": rationale,
                    },
                    "experiment_question": (
                        f"在保持 parent 信号机制不变时，{change_type} 是否改善净收益与稳定性？"
                    ),
                    "expected_failure_modes": [
                        "平滑过度导致信号衰减或延迟",
                        "优化后换手、相关性或健康检查恶化",
                    ],
                    "tuning_risk": True,
                    "experiment_stage": "CHILD",
                    "change_type": change_type,
                    "parent_expression": base,
                    "changed_variable": change_type,
                    "research_role": "EXPLOIT",
                    "lineage_id": parent.get("lineage_id") or parent.get("hypothesis_id"),
                    "template_id": f"auto_opt_{change_type}",
                    "template_family": "autonomous_optimization",
                    "template_stage_path": "L0:completed signal -> L1:one-variable optimization",
                    "template_ref": {"source": "newwqb_autonomous_optimizer",
                                     "parent": identity},
                    "template_slots": {"parent": base},
                    "rationale": rationale,
                    "direction": parent.get("direction") or "long",
                    "expected_horizon": parent.get("expected_horizon") or "short-term",
                    "falsification": "若 Sharpe/Fitness 或换手健康恶化，则关闭该优化分支。",
                })
                out.append(proposal)
                excluded.add(normalized)
        return out

    def assemble_proposals(self, hypothesis, fields, operator_reference,
                           max_candidates=8, excluded_expressions=None):
        """Create auditable EXPLORE proposals from one discovery bundle.

        This is the unattended factory's deterministic AI adapter: it only
        uses non-UNKNOWN discovery profiles and emits a minimal BASELINE per
        field/template.  It does not invent a platform fact; the mechanism is
        explicitly recorded as a test rationale and remains subject to the
        normal production preflight.
        """
        if not isinstance(hypothesis, dict) or not isinstance(fields, list):
            return []
        try:
            limit = max(0, int(max_candidates))
        except (TypeError, ValueError):
            return []
        if limit == 0 or not isinstance(operator_reference, dict):
            return []
        operators = {
            str(operator) for operator in (operator_reference.get("operators") or [])
            if isinstance(operator, (str, int))
        }
        excluded = {
            canonical_expression(value)
            for value in (excluded_expressions or [])
            if isinstance(value, str) and value.strip()
        }
        source_default = hypothesis.get("field_source")
        assembled = []
        used_fields = set()
        economic_mode = str(hypothesis.get("template_mode") or "").lower() == "economic"
        vector_template_id = (
            "vector_persistent_signal" if economic_mode else "vector_mean_rank"
        )
        template_order = (
            [template.template_id for template in self.registry.economic_templates()]
            if economic_mode else [
                "rank_level", "zscore_level", "reversal_zscore_20",
                "momentum_mean_20", "change_delta_5", "vector_mean_rank",
            ]
        )
        family_counts = {}
        for offset, profile in enumerate(fields):
            if not isinstance(profile, dict):
                continue
            raw_field_id = profile.get("id")
            if not isinstance(raw_field_id, (str, int)):
                continue
            field_id = str(raw_field_id)
            description = profile.get("description")
            if not field_id or not isinstance(description, str) or not description.strip():
                continue
            if str(profile.get("semantic_status", "UNKNOWN")).upper() == "UNKNOWN":
                continue
            field_type = str(profile.get("type") or "").upper()
            if field_id in used_fields:
                continue
            selected = None
            # If the preferred skeleton was already seen, rotate through the
            # bounded catalog for this field instead of repeatedly emitting an
            # empty round.  This preserves one candidate per field while
            # turning exact-expression dedupe into useful structural novelty.
            for step in range(len(template_order)):
                template_id = template_order[(offset + step) % len(template_order)]
                if template_id == vector_template_id and field_type != "VECTOR":
                    template_id = "rank_level"
                if template_id != vector_template_id and field_type == "VECTOR":
                    template_id = vector_template_id
                template = self.registry.get(template_id)
                if template is None:
                    continue
                family_cap = 4 if economic_mode else MAX_TEMPLATE_FAMILY_PER_BATCH
                if family_counts.get(template.family, 0) >= family_cap:
                    continue
                generated = self.generate(
                    dict(hypothesis, template_ids=[template_id]), [field_id], count=1
                )
                if not generated:
                    continue
                generated_candidate = generated[0]
                generated_expression = generated_candidate["expression"]
                if canonical_expression(generated_expression) in excluded:
                    continue
                actual_ops = list(analyze_expression(generated_expression).operators)
                if not set(actual_ops).issubset(operators):
                    continue
                selected = (template, generated_candidate, actual_ops)
                break
            if selected is None:
                continue
            template, candidate, actual_ops = selected
            field_source = profile.get("field_source") or source_default
            if not isinstance(field_source, dict):
                field_source = {"kind": "unknown", "path": None, "snapshot_date": None}
            proposal = {
                "expression": candidate["expression"],
                "fields": [field_id],
                "datasets": ([profile.get("dataset")] if profile.get("dataset")
                              else list(hypothesis.get("datasets") or [])),
                "field_understanding": {
                    field_id: f"基于本轮 discovery 原文：{description}"
                },
                "field_analysis": {
                    field_id: {
                        "semantic": description,
                        "coverage": profile.get("coverage"),
                        "frequency": profile.get("frequency"),
                        "data_type": profile.get("type"),
                    }
                },
                "field_source": field_source,
                "field_hypothesis_basis": {
                    field_id: {
                        "description": description,
                        "mechanism": candidate["rationale"],
                        "independent_increment": "该 BASELINE 只检验这一字段的独立增量信息。",
                        "direction": "reversal" if "reversal" in template.family else "long",
                    }
                },
                "economic_mechanism": candidate["economic_mechanism"],
                "direction_transform": candidate["direction_transform"],
                "operator_mapping": candidate["rationale"],
                "operator_evidence": {
                    "sha256": operator_reference.get("sha256"),
                    "operators": actual_ops,
                    "rationale": candidate["rationale"],
                },
                "experiment_question": (
                    f"字段 {field_id} 的 {template.template_id} 结构是否提供可复现的增量信号？"
                ),
                "expected_failure_modes": [
                    "字段覆盖不足或缺失导致有效持仓减少",
                    "信号集中或换手异常导致健康检查失败",
                ],
                "tuning_risk": False,
                "experiment_stage": "BASELINE",
                "change_type": "baseline",
                "research_role": "EXPLORE",
                "lineage_id": f"{hypothesis.get('id', 'factory')}:field:{field_id}",
                "signal_family": f"{template.family}:{field_id}",
                "expected_quality": 1.0,
                "information_gain": 1.0,
                "novelty": 1.0,
                "simulation_cost": 1.0,
                "rationale": candidate["rationale"],
                "direction": "reversal" if "reversal" in template.family else "long",
                "expected_horizon": "short-term",
                "falsification": "若六指标、checks 或健康诊断不能支持稳定增量，则关闭该字段-结构组合。",
                "self_correlation_impact": {
                    "expected_effect": "UNKNOWN",
                    "basis": "no_live_behavior_series",
                    "rationale": "模拟前没有平台结算值，不把结构差异冒充为低自相关。",
                    "admission": "REVIEW",
                },
            }
            proposal.update({
                key: candidate[key]
                for key in ("mutation", "template_id", "template_family",
                            "template_stage_path", "template_ref", "template_slots",
                            "factory_version")
            })
            assembled.append(proposal)
            excluded.add(canonical_expression(proposal["expression"]))
            used_fields.add(field_id)
            family_counts[template.family] = family_counts.get(template.family, 0) + 1
            if len(assembled) >= limit:
                break
        return assembled
