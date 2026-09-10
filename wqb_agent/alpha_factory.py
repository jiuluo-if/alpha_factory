"""Template-first Alpha candidate factory.

This is a proposal-construction layer only.  It does not call BRAIN, write
research state, or submit simulations.  A template describes the structural
shape of an Alpha; a field bundle supplies the slots.  The resulting metadata
keeps the skeleton visible to the later proposal and diversity gates.
"""

import hashlib
import itertools
import json
import math
import random
from dataclasses import dataclass

from .discovery import frequency_evidence, normalize_coverage
from .diversity import extract_fields
from .expression import analyze_expression, canonical_expression
from .research_guard import overfit_expression_reason, parameter_only_change_reason


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
    # Generic slot names are intentional: ``data_field`` is the semantic
    # primary field selected from the current dataset catalog, not a literal
    # field called data_field.  This keeps templates reusable for low/high/
    # close/volume and for platform fields with different names.
    AlphaTemplate(
        "generic_pair_spread_change", "generic_multi_field_spread",
        "rank(ts_delta(subtract({data_field}, {s}), 5))",
        required_slots=("data_field", "s"),
        stage_path="L0:generic fields -> L1:spread -> L2:delta -> L3:rank",
        rationale="用动态主字段与语义互补字段的差值检验相对变化，不绑定 low 等具体字段名。",
        economic=True,
    ),
    AlphaTemplate(
        "generic_pair_ratio_extreme", "generic_multi_field_ratio",
        "rank(ts_zscore(divide({data_field}, add(abs({s}), 0.001)), 20))",
        required_slots=("data_field", "s"),
        stage_path="L0:generic fields -> L1:safe ratio -> L2:zscore -> L3:rank",
        rationale="对任意可兼容字段构造受保护比例，检验相对极端状态而非字段名称本身。",
        economic=True,
    ),
    AlphaTemplate(
        "generic_triple_confirmation", "generic_multi_field_confirmation",
        "rank(add(ts_zscore({data_field}, 20), add(ts_zscore({s}, 20), ts_zscore({t}, 20))))",
        required_slots=("data_field", "s", "t"),
        stage_path="L0:generic fields -> L1:three standardized legs -> L2:additive confirmation -> L3:rank",
        rationale="将三个动态选择的互补字段标准化后检验一致性确认，避免把 low 等名称硬编码成机制。",
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


_SEMANTIC_CONCEPT_RULES = (
    ("data_quality", ("missing", "null", "nan", "quality", "coverage", "stale")),
    ("analyst_revision", ("revision", "revised", "estimate change", "forecast change")),
    ("option_relative", ("put call", "put-call", "putcall", "iv skew")),
    ("liquidity", ("open interest", "option volume", "liquidity", "trading volume", "dollar volume", "turnover", "bid ask", "bid-ask")),
    ("volatility", ("volatility", "implied vol", "realized vol", "iv_skew", "variance")),
    ("event_count", ("mention count", "event count", "number of events", "occurrence", "filing count")),
    ("sentiment", ("sentiment", "social", "news", "recommendation", "bullish", "bearish")),
    ("valuation", ("valuation", "target price", "price target", "price-to", "price to", "multiple", "p/e", "p/b")),
    ("earnings", ("earnings", "eps", "revenue", "sales", "profit", "cash flow", "fscore")),
    ("fundamental", ("total assets", "assets", "liabilities", "equity", "book value", "debt", "fundamental")),
    ("market_price", ("price", "close", "open", "high", "low", "vwap", "return")),
)

_SEMANTIC_MEASUREMENT_RULES = (
    ("dispersion", ("dispersion", "skew", "spread", "standard deviation", "std dev")),
    ("ratio", ("ratio", "percent", "%", "margin", "yield", "multiple", "p/e", "p/b")),
    ("change", ("revision", "revised", "change", "delta", "growth", "return", "momentum", "surprise", "diff")),
    ("count", ("count", "number", "mentions", "events", "occurrence", "volume")),
    ("probability", ("probability", "likelihood", "rating", "recommendation")),
)

_SEMANTIC_RELATION_LABELS = {
    "same_economic_concept",
    "numerator_denominator",
    "complementary_expectations",
    "comparable_scale",
    "price_volume",
    "option_pair",
    "revision_dispersion",
}


def _semantic_profile_text(profile, *, include_dataset=True):
    """Build semantic evidence only from the documented field profile keys."""
    if not isinstance(profile, dict):
        return ""
    values = []
    keys = ("id", "name", "description")
    if include_dataset:
        keys = (*keys, "dataset", "frequency", "category")
    for key in keys:
        value = profile.get(key)
        if isinstance(value, dict):
            value = value.get("id") or value.get("name")
        if value is not None:
            values.append(str(value))
    return " ".join(values).lower().replace("_", " ")


def _semantic_has(text, phrase):
    phrase = str(phrase).lower()
    if not phrase:
        return False
    if any(char.isalnum() for char in phrase):
        return phrase in text
    return phrase in text


def _semantic_frequency_text(profile):
    value = profile.get("frequency") if isinstance(profile, dict) else None
    if isinstance(value, dict):
        value = value.get("name") or value.get("id")
    return str(value or "").lower()


def _derive_field_semantic_traits(profile):
    """Derive a conservative, non-persistent semantic view of one profile."""
    if not isinstance(profile, dict):
        return {
            "concept": "unknown",
            "measurement": "unknown",
            "behavior": "unknown",
            "frequency": "unknown",
            "sign_semantics": "unknown",
            "direction_meaning": "unknown",
            "update_style": "unknown",
            "tags": [],
            "status": "UNKNOWN",
            "semantic_admission": "UNKNOWN",
            "metadata_semantics": "UNKNOWN",
        }
    text = _semantic_profile_text(profile)
    # Category and dataset are fallback context, not direct field evidence.
    # Keep them out of the high-confidence admission path.
    direct_text = _semantic_profile_text(profile, include_dataset=False)
    category = str(profile.get("category") or "").lower()
    frequency = _semantic_frequency_text(profile)

    concept = "unknown"
    concept_hits = []
    direct_concept_hits = []
    for candidate, keywords in _SEMANTIC_CONCEPT_RULES:
        hits = [word for word in keywords if _semantic_has(text, word)]
        if hits:
            concept = candidate
            concept_hits = hits
            direct_concept_hits = [
                word for word in keywords if _semantic_has(direct_text, word)
            ]
            break
    if concept == "unknown":
        category_rules = {
            "analyst": "analyst",
            "option": "option",
            "options": "option",
            "fundamental": "fundamental",
            "social": "sentiment",
            "news": "sentiment",
            "liquidity": "liquidity",
        }
        concept = category_rules.get(category, "unknown")
        concept_hits = [category] if concept != "unknown" else []
        direct_concept_hits = []

    measurement = "level"
    measurement_hits = []
    for candidate, keywords in _SEMANTIC_MEASUREMENT_RULES:
        hits = [word for word in keywords if _semantic_has(text, word)]
        if hits:
            measurement = candidate
            measurement_hits = hits
            break
    if concept == "analyst_revision":
        measurement = "change"
        if "revision" not in measurement_hits:
            measurement_hits = ["revision"] + measurement_hits
    if concept == "event_count":
        measurement = "count"
    if (
        measurement == "dispersion"
        and "analyst" in direct_text
        and concept != "analyst_revision"
    ):
        concept = "analyst_dispersion"
        concept_hits = ["analyst", "dispersion"]
        direct_concept_hits = ["analyst", "dispersion"]

    frequency_slow = any(
        marker in frequency for marker in ("quarter", "monthly", "month", "annual", "year", "weekly", "week")
    )
    frequency_fast = any(
        marker in frequency for marker in ("intraday", "minute", "hour", "daily", "day")
    )
    event_signal = concept in {
        "analyst_revision", "analyst_dispersion", "event_count", "sentiment"
    }
    slow_signal = frequency_slow or concept in {"fundamental", "earnings", "valuation"} and not frequency_fast
    sparse = False
    coverage = normalize_coverage(profile)
    sparse = coverage is not None and coverage < 0.5
    if slow_signal:
        behavior = "slow_moving"
    elif event_signal:
        behavior = "event_driven"
    elif sparse:
        behavior = "sparse"
    elif measurement in {"change", "dispersion"} or concept in {"market_price", "volatility", "liquidity"}:
        behavior = "signed"
    elif measurement in {"ratio", "probability"}:
        behavior = "bounded"
    elif measurement == "count" or concept in {"event_count", "fundamental"}:
        behavior = "nonnegative"
    else:
        behavior = "unknown"

    if event_signal:
        update_style = "event_driven"
    elif slow_signal:
        update_style = "periodic"
    elif frequency_fast:
        update_style = "continuous"
    else:
        update_style = "unknown"

    if concept == "analyst_revision" or measurement == "change":
        sign_semantics = "signed_change"
    elif concept in {"volatility", "event_count", "fundamental", "earnings", "data_quality"}:
        sign_semantics = "nonnegative_level"
    elif measurement == "dispersion":
        sign_semantics = "nonnegative_dispersion"
    elif measurement in {"ratio", "probability"}:
        sign_semantics = "bounded"
    elif concept in {"market_price", "sentiment"}:
        sign_semantics = "signed_level"
    elif concept == "liquidity":
        sign_semantics = "nonnegative_level"
    else:
        sign_semantics = "unknown"

    direction_meaning = {
        "analyst_revision": "information_update",
        "analyst_dispersion": "expectation_dispersion",
        "option_relative": "relative_option_position",
        "option": "option_measurement",
        "volatility": "risk_exposure",
        "event_count": "attention_events",
        "liquidity": "market_participation",
        "sentiment": "attention_or_belief",
        "valuation": "relative_value",
        "earnings": "operating_expectation",
        "fundamental": "economic_scale",
        "market_price": "market_level",
        "data_quality": "data_availability",
    }.get(concept, "unknown")

    tags = set()
    if concept == "market_price" or any(word in text for word in ("price", "close", "high", "low", "vwap")):
        tags.add("price")
    if concept == "liquidity" or any(word in text for word in ("volume", "turnover", "liquidity")):
        tags.add("volume")
    if concept == "volatility":
        tags.add("volatility")
    if concept == "option_relative":
        tags.add("relative")
    if "option" in text or "call" in text or "put" in text:
        tags.add("option")
    if "put" in text:
        tags.add("option_put")
    if "call" in text:
        tags.add("option_call")
    if concept == "analyst_revision" or "analyst" in text:
        tags.add("analyst")
    if measurement == "dispersion":
        tags.add("dispersion")
    if concept == "event_count":
        tags.add("event_count")
    if concept in {"fundamental", "earnings", "valuation"}:
        tags.add("fundamental_scale")
    if any(word in text for word in ("revenue", "sales", "earnings", "eps", "profit", "cash flow")):
        tags.add("earnings")
    if any(word in text for word in ("assets", "equity", "book value", "debt")):
        tags.add("asset_scale")
    if any(word in text for word in ("social", "news", "mention")):
        tags.add("attention")
    semantic_admission = (
        "ALLOW" if direct_concept_hits else
        "REVIEW" if concept != "unknown" else "UNKNOWN"
    )
    metadata_semantics = (
        "AVAILABLE" if str(profile.get("description") or "").strip()
        else "UNKNOWN"
    )
    if metadata_semantics != "AVAILABLE" and semantic_admission == "ALLOW":
        semantic_admission = "REVIEW"
    return {
        "concept": concept,
        "measurement": measurement,
        "behavior": behavior,
        "frequency": frequency or "unknown",
        "sign_semantics": sign_semantics,
        "direction_meaning": direction_meaning,
        "update_style": update_style,
        "tags": sorted(tags),
        "status": "KNOWN" if concept != "unknown" and direct_concept_hits else "UNKNOWN",
        "confidence": "HIGH" if direct_concept_hits else "LOW",
        "semantic_admission": semantic_admission,
        "metadata_semantics": metadata_semantics,
        "evidence": {
            "concept": concept_hits,
            "direct_concept": direct_concept_hits,
            "measurement": measurement_hits,
            "frequency": frequency,
        },
    }


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
        self.last_feasibility = None

    def assess_feasibility(self, hypothesis, fields, operator_reference,
                           *, excluded_expressions=(), probe_id=None,
                           max_combinations=256):
        """Run a bounded control-plane feasibility probe before assembly."""
        profiles = [field for field in (fields or []) if (
            isinstance(field, dict)
            and field.get("id") is not None
            and str(field.get("description") or "").strip()
            and str(field.get("semantic_status", "UNKNOWN")).upper() != "UNKNOWN"
        )]
        frequency_counts = {
            "explicit": 0, "inferred": 0, "unknown": 0,
        }
        for profile in profiles:
            source = frequency_evidence(profile)["source"]
            if source == "EXPLICIT_PLATFORM":
                frequency_counts["explicit"] += 1
            elif source == "DESCRIPTION_INFERRED":
                frequency_counts["inferred"] += 1
            else:
                frequency_counts["unknown"] += 1
        templates = list(self.registry.economic_templates())
        excluded = {canonical_expression(value) for value in excluded_expressions
                    if isinstance(value, str) and value.strip()}
        candidate_expressions = set()
        counts = {
            "pair_examined": 0, "triple_examined": 0,
            "relationship_allow": 0, "relationship_review": 0,
            "relationship_unknown": 0, "relationship_incompatible": 0,
            "frequency_incompatible": 0, "template_compatible_count": 0,
            "historical_expression_exclusion_count": 0,
            "candidates_before_dedupe": 0, "candidates_after_dedupe": 0,
            "novel_cross_dataset_relationship_count": 0,
            "proposal_contract_rejection_count": 0,
        }
        candidate_fingerprints = set()
        relationship_fingerprints = set()
        mechanism_families = set()
        combinations_seen = 0
        for template in templates:
            slots = len(template.required_slots)
            if slots < 2:
                continue
            iterator = itertools.combinations(profiles, slots)
            for selected in iterator:
                combinations_seen += 1
                if combinations_seen > max(1, int(max_combinations)):
                    break
                if slots == 2:
                    counts["pair_examined"] += 1
                else:
                    counts["triple_examined"] += 1
                relation = self._relationship_gate(list(selected), template)
                admission = relation["admission"]
                if admission == "ALLOW":
                    counts["relationship_allow"] += 1
                elif admission == "REVIEW":
                    counts["relationship_review"] += 1
                else:
                    counts["relationship_incompatible"] += 1
                frequency_status = relation["frequency_compatibility"]["status"]
                if frequency_status == "INCOMPATIBLE":
                    counts["frequency_incompatible"] += 1
                if admission != "ALLOW":
                    if admission == "REVIEW":
                        counts["relationship_unknown"] += 1
                    continue
                mechanism_families.add(str(template.family))
                relationship_fingerprints.add(
                    f"{template.family}:{','.join(sorted(str(p.get('id')) for p in selected))}"
                )
                try:
                    values = {
                        slot: str(profile.get("id"))
                        for slot, profile in zip(template.required_slots, selected)
                    }
                    values["g"] = self.neutralization
                    expression = canonical_expression(template.expression.format(**values))
                except (KeyError, ValueError):
                    counts["proposal_contract_rejection_count"] += 1
                    continue
                counts["template_compatible_count"] += 1
                counts["candidates_before_dedupe"] += 1
                if expression in excluded:
                    counts["historical_expression_exclusion_count"] += 1
                    continue
                if expression in candidate_expressions:
                    continue
                candidate_expressions.add(expression)
                if len(candidate_fingerprints) < 64:
                    candidate_fingerprints.add(expression)
                counts["candidates_after_dedupe"] += 1
                datasets = {str(profile.get("dataset")) for profile in selected}
                if len(datasets) > 1:
                    counts["novel_cross_dataset_relationship_count"] += 1
            if combinations_seen > max(1, int(max_combinations)):
                break
        taxonomy = "READY"
        if not profiles:
            taxonomy = "FIELD_SEMANTICS_INSUFFICIENT"
        elif frequency_counts["explicit"] + frequency_counts["inferred"] == 0:
            taxonomy = "FREQUENCY_EVIDENCE_INSUFFICIENT"
        elif counts["frequency_incompatible"] and not counts["relationship_allow"]:
            taxonomy = "FREQUENCY_INCOMPATIBLE"
        elif counts["relationship_review"] and not counts["relationship_allow"]:
            taxonomy = "RELATIONSHIP_REVIEW"
        elif counts["candidates_before_dedupe"] and not counts["candidates_after_dedupe"]:
            taxonomy = "MECHANISM_FAMILY_EXHAUSTED"
        elif not counts["template_compatible_count"]:
            taxonomy = "TEMPLATE_INCOMPATIBLE"
        elif not counts["novel_cross_dataset_relationship_count"]:
            taxonomy = "CROSS_DATASET_FEASIBILITY_ZERO"
        result = {
            "probe_id": str(probe_id or (hypothesis or {}).get("id") or "probe"),
            "field_total": len(fields or []), "semantic_known": len(profiles),
            "explicit_frequency_count": frequency_counts["explicit"],
            "inferred_frequency_count": frequency_counts["inferred"],
            "unknown_frequency_count": frequency_counts["unknown"],
            "dataset_count": len({str(p.get("dataset")) for p in profiles if p.get("dataset") is not None}),
            "mechanism_family": sorted(mechanism_families)[0] if len(mechanism_families) == 1 else "mixed",
            "dataset_route": sorted({str(p.get("dataset")) for p in profiles if p.get("dataset") is not None}),
            "candidate_expression_fingerprints": sorted(candidate_fingerprints),
            "relationship_fingerprints": sorted(relationship_fingerprints)[:64],
            "failure_taxonomy": taxonomy,
            "batch_gate": {
                "feasible": counts["novel_cross_dataset_relationship_count"] > 0,
                "reason": taxonomy,
            },
            **counts,
        }
        self.last_feasibility = result
        return result

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
        normalized_profiles = []
        seen_profile_keys = set()
        for field in fields:
            field_id = field.get("id") if isinstance(field, dict) else field
            if not isinstance(field_id, (str, int)) or not field:
                continue
            field_id = str(field_id)
            dataset = field.get("dataset") if isinstance(field, dict) else None
            dataset = str(dataset) if dataset is not None else None
            profile_key = (dataset, field_id)
            if profile_key in seen_profile_keys:
                continue
            seen_profile_keys.add(profile_key)
            normalized.append(field_id)
            normalized_profiles.append(
                dict(field) if isinstance(field, dict) else {"id": field_id}
            )
        if not normalized:
            return []
        primary = normalized[0]
        secondary = normalized[1] if len(normalized) > 1 else None
        tertiary = normalized[2] if len(normalized) > 2 else None
        ref_input = hypothesis.get("template_ref") or {}
        candidates = []
        seen = set()
        for template in self.registry.select(hypothesis):
            values = {
                "p": primary,
                "data_field": primary,
                "s": secondary,
                "t": tertiary,
                "g": self.neutralization,
            }
            if any(
                slot in {"p", "data_field", "s", "t"}
                and not values.get(slot)
                for slot in template.required_slots
            ):
                continue
            slot_profiles = list(normalized_profiles[:len(template.required_slots)])
            if len(template.required_slots) > 1:
                relation = self._relationship_gate(slot_profiles, template)
                if relation["admission"] != "ALLOW":
                    continue
            else:
                relation = None
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
            slot_values = {"p": primary, "data_field": primary,
                           "g": self.neutralization}
            for slot in ("s", "t"):
                if values.get(slot):
                    slot_values[slot] = values[slot]
            relationship_audit = None
            if relation is not None:
                relationship_audit = {
                    "slot_assignment": {
                        slot: values[slot]
                        for slot in template.required_slots
                        if slot in values and values[slot]
                    },
                    "relationship_type": relation["relationship_type"],
                    "relationship_admission": relation["admission"],
                    "relationship_reason": list(relation["reasons"]),
                    "slot_assignment_reason": relation["slot_assignment_reason"],
                    "frequency_compatibility": relation["frequency_compatibility"],
                    "symmetric": relation["symmetric"],
                }
            used_ids = extract_fields(expression, normalized)
            profile_by_id = {}
            for profile in normalized_profiles:
                profile_by_id.setdefault(str(profile.get("id")), profile)
            # Keep references in slot/input order.  ``extract_fields`` is
            # intentionally canonical (length-sorted) for parsing, while a
            # template audit must show which profile filled p/data_field/s/t.
            field_refs = []
            for profile in normalized_profiles:
                field_id = str(profile.get("id"))
                if field_id not in used_ids:
                    continue
                field_refs.append({
                    "id": field_id,
                    "dataset": profile.get("dataset"),
                })
            candidates.append(
                {
                    "expression": expression,
                    "rationale": template.rationale,
                    "mutation": f"template:{template.template_id}",
                    "parent": None,
                    "fields_used": used_ids,
                    "field_refs": field_refs,
                    "template_id": template.template_id,
                    "template_family": template.family,
                    "template_stage_path": template.stage_path,
                    "template_ref": ref,
                    "template_slots": slot_values,
                    "relationship_audit": relationship_audit,
                    "factory_version": "alpha-factory-v1",
                    "economic_mechanism": self._field_mechanism(
                        normalized_profiles[0],
                        _derive_field_semantic_traits(normalized_profiles[0]),
                        template,
                        relation,
                    ),
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

    @staticmethod
    def _profile_dataset(profile):
        value = profile.get("dataset") if isinstance(profile, dict) else None
        return str(value) if value is not None else None

    @classmethod
    def _profile_key(cls, profile):
        if not isinstance(profile, dict):
            return (None, None)
        value = profile.get("id")
        return cls._profile_dataset(profile), str(value) if value is not None else None

    @staticmethod
    def derive_field_semantic_traits(profile):
        """Return a derived semantic view without changing the field profile."""
        return _derive_field_semantic_traits(profile)

    @staticmethod
    def _template_semantic_compatibility(template, profile, traits=None):
        """Score unary template fit; unknown semantics remain explicitly weak."""
        traits = traits or _derive_field_semantic_traits(profile)
        family = template.family
        concept = traits["concept"]
        measurement = traits["measurement"]
        behavior = traits["behavior"]
        frequency = traits["frequency"]
        sign_semantics = traits["sign_semantics"]
        known = traits.get("semantic_admission") == "ALLOW"
        field_type = str(profile.get("type") or "").upper()
        reasons = []
        score = 0

        vector_family = family.startswith("vector_") or family == "vector_aggregation"
        uses_vector = "vec_avg" in template.expression or "vec_sum" in template.expression
        if uses_vector != (field_type == "VECTOR"):
            return {"admission": "REJECT", "score": -100, "reasons": ["VECTOR 类型不匹配"]}
        if field_type == "VECTOR" and not uses_vector:
            return {"admission": "REJECT", "score": -100, "reasons": ["VECTOR 只能进入向量聚合模板"]}

        if family in {"quality_change", "data_resilient_change", "group_data_repair", "data_quality_penalty", "stale_information"}:
            if concept != "data_quality":
                return {"admission": "REJECT", "score": -30, "reasons": ["模板要求 data_quality 语义"]}
            score += 60
            reasons.append("字段语义明确指向数据质量")
        elif family == "event_trigger":
            if (not known or behavior != "event_driven"
                    or frequency in {"weekly", "monthly", "quarterly", "annual"}):
                return {"admission": "REJECT", "score": -30, "reasons": ["缺少事件驱动语义证据"]}
            score += 65
            reasons.append("字段以事件驱动方式更新")
        elif family in {"risk_adjusted_reversal", "downside_risk"}:
            if concept not in {"volatility", "market_price", "liquidity", "analyst_revision"}:
                if known:
                    return {"admission": "REJECT", "score": -20, "reasons": ["风险模板与字段概念不匹配"]}
            score += 55 if concept == "volatility" else 30
            reasons.append("模板把字段变化解释为风险或异常暴露")
        elif family in {"persistent_level", "momentum", "change", "innovation_surprise", "delayed_confirmation",
                        "accumulated_change", "distribution_regime", "adaptive_scale_change", "trend_residual",
                        "compounding_pressure", "turnover_control", "distributional_change", "group_relative_change",
                        "group_relative_extreme", "group_centered_level", "extreme_location", "extreme_low"}:
            if known and concept == "data_quality":
                return {"admission": "REJECT", "score": -20, "reasons": ["数据质量不是该模板的经济输入"]}
            if concept == "analyst_revision":
                score += 65 if family in {"change", "innovation_surprise", "delayed_confirmation", "persistent_level"} else 45
                reasons.append("分析师修正体现信息更新或扩散过程")
            elif measurement in {"change", "dispersion"}:
                score += 48
                reasons.append("字段提供可观察的变化或离散程度")
            elif measurement == "level" and family in {"persistent_level", "distribution_regime", "group_centered_level"}:
                score += 42
                reasons.append("字段水平适合检验相对状态与持续性")
            else:
                score += 22
                reasons.append("字段可作为有限的时间序列基线")
        elif family in {"robust_cross_section", "rank_level", "zscore_level", "group_neutralized", "cross_sectional_rank",
                        "cross_sectional_standardize"}:
            score += 32
            reasons.append("横截面基线不依赖绝对尺度")

        if concept == "volatility":
            if family in {"risk_adjusted_reversal", "downside_risk"}:
                score += 30
                reasons.append("波动率直接支持风险暴露或风险调整机制")
            elif family == "distribution_regime":
                score += 24
                reasons.append("波动率适合风险状态或 regime 表达")
            elif family in {"relative_spread_change", "relative_ratio",
                            "relative_covariance", "relative_correlation",
                            "generic_multi_field_spread", "generic_multi_field_ratio"}:
                score += 18
                reasons.append("波动率可与价格或另一风险量构成相对关系")
        if concept == "analyst_revision":
            if family in {"change", "persistent_level", "innovation_surprise",
                          "delayed_confirmation"}:
                score += 35
                reasons.append("修正字段直接观测预期更新、持续性或滞后确认")
            elif family == "event_trigger":
                score -= 25
                reasons.append("修正虽是更新事件，但优先测试变化本身而非极端触发")
        if behavior == "slow_moving":
            if family == "event_trigger":
                return {"admission": "REJECT", "score": -30, "reasons": ["慢变字段不默认进入事件触发"]}
            if family in {"persistent_level", "distribution_regime", "group_centered_level"}:
                score += 24
                reasons.append("低频字段更适合检验持久状态或历史 regime")
        if sign_semantics == "nonnegative_level" and family in {
                "reversal", "risk_adjusted_reversal", "downside_risk"}:
            score -= 8
            reasons.append("非负水平字段不把符号方向直接解释为反转")
        if concept == "analyst_revision" and family == "data_quality_penalty":
            return {"admission": "REJECT", "score": -30, "reasons": ["修正字段不能冒充数据质量"]}
        if not known:
            if vector_family or template.required_slots != ("p",):
                return {"admission": "REVIEW", "score": score - 15, "reasons": ["语义 UNKNOWN，仅可审阅"]}
            return {"admission": "REVIEW", "score": score - 10, "reasons": ["语义 UNKNOWN，仅可作语法基线"]}
        if not reasons:
            return {"admission": "REVIEW", "score": 0, "reasons": ["没有足够的经济兼容证据"]}
        return {"admission": "ALLOW", "score": score, "reasons": reasons}

    @classmethod
    def _relationship_labels(cls, left, right):
        """Infer only explicit economic relationships from two field traits."""
        left_tags = set(left.get("tags") or [])
        right_tags = set(right.get("tags") or [])
        left_concept = left.get("concept")
        right_concept = right.get("concept")
        labels = set()
        if left_concept == right_concept and left_concept != "unknown":
            labels.add("same_economic_concept")
        if {left_concept, right_concept} == {"market_price", "liquidity"}:
            labels.add("price_volume")
        if (
            left_concept == right_concept == "volatility"
            and {"option_put", "option_call"}.issubset(left_tags | right_tags)
            and bool(left_tags & {"option_put", "option_call"})
            and bool(right_tags & {"option_put", "option_call"})
        ):
            labels.add("option_pair")
        if ("analyst" in left_tags and "dispersion" in right_tags
                or "analyst" in right_tags and "dispersion" in left_tags):
            labels.add("revision_dispersion")
        if {"price", "volatility"}.issubset(left_tags | right_tags):
            labels.add("complementary_expectations")
        if {"price", "fundamental_scale"}.issubset(left_tags | right_tags):
            labels.add("comparable_scale")
        if {"asset_scale", "earnings"}.issubset(left_tags | right_tags):
            labels.add("numerator_denominator")
        if {left_concept, right_concept} in (
            {"earnings", "valuation"}, {"fundamental", "valuation"},
        ):
            labels.add("numerator_denominator")
        return labels

    @staticmethod
    def _frequency_bucket(value):
        text = str(value or "").lower()
        if any(marker in text for marker in ("intraday", "minute", "hour")):
            return "intraday"
        if any(marker in text for marker in ("daily", "day")):
            return "daily"
        if any(marker in text for marker in ("weekly", "week")):
            return "weekly"
        if any(marker in text for marker in ("monthly", "month")):
            return "monthly"
        if "quarter" in text:
            return "quarterly"
        if any(marker in text for marker in ("annual", "year")):
            return "annual"
        return "unknown"

    @classmethod
    def _frequency_compatibility(cls, traits, family):
        """Classify only obvious frequency conflicts for a relation."""
        buckets = [cls._frequency_bucket(item.get("frequency")) for item in traits]
        if any(bucket == "unknown" for bucket in buckets):
            return {
                "status": "REVIEW",
                "buckets": buckets,
                "reasons": ["frequency evidence is incomplete; relationship needs review"],
            }
        if len(set(buckets)) == 1:
            return {
                "status": "COMPATIBLE",
                "buckets": buckets,
                "reasons": [f"frequency compatible: {buckets[0]}"],
            }
        rank = {
            "intraday": 0, "daily": 1, "weekly": 2,
            "monthly": 3, "quarterly": 4, "annual": 5,
        }
        spread = max(rank[bucket] for bucket in buckets) - min(
            rank[bucket] for bucket in buckets
        )
        direct_dependence = family in {"relative_covariance", "relative_correlation"}
        if direct_dependence and spread >= 2:
            return {
                "status": "INCOMPATIBLE",
                "buckets": buckets,
                "reasons": [
                    "frequency incompatible for direct co-movement: "
                    + " vs ".join(buckets)
                ],
            }
        if direct_dependence and any(
            item.get("concept") == "event_count" for item in traits
        ) and any(
            item.get("concept") in {"fundamental", "earnings", "valuation"}
            for item in traits
        ) and spread >= 1:
            return {
                "status": "INCOMPATIBLE",
                "buckets": buckets,
                "reasons": [
                    "frequency incompatible for event-to-fundamental co-movement: "
                    + " vs ".join(buckets)
                ],
            }
        return {
            "status": "REVIEW",
            "buckets": buckets,
            "reasons": [
                "frequency requires review: " + " vs ".join(buckets)
            ],
        }

    @staticmethod
    def _relationship_type(labels):
        for label in (
            "option_pair", "revision_dispersion", "numerator_denominator",
            "same_economic_concept", "comparable_scale", "price_volume",
            "complementary_expectations",
        ):
            if label in labels:
                return label
        return "unknown"

    @classmethod
    def _relationship_gate(cls, profiles, template):
        """Return an auditable relation decision for pair/triple slots."""
        traits = [_derive_field_semantic_traits(profile) for profile in profiles]
        family = template.family
        frequency = cls._frequency_compatibility(traits, family)

        def result(admission, score, labels, relationship_type="unknown",
                   *, symmetric=False, preferred=None, assignment_reason="",
                   evidence_strength="LOW", confirmation_mechanism=None,
                   reasons=()):
            all_reasons = list(reasons) + list(frequency["reasons"])
            return {
                "admission": admission,
                "score": score,
                "evidence_strength": evidence_strength,
                "labels": sorted(labels),
                "relationship_type": relationship_type,
                "reasons": all_reasons,
                "preferred_slot_assignment": preferred or "UNRESOLVED",
                "slot_assignment_reason": assignment_reason,
                "symmetric": bool(symmetric),
                "asymmetric": not bool(symmetric),
                "frequency_compatibility": frequency,
                "confirmation_mechanism": confirmation_mechanism,
            }

        if any(item.get("semantic_admission") != "ALLOW" for item in traits):
            return result(
                "REVIEW", 0, [], reasons=(
                    "至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系",
                )
            )

        pair_labels = [
            cls._relationship_labels(left, right)
            for left, right in itertools.combinations(traits, 2)
        ]
        labels = set().union(*pair_labels) if pair_labels else set()

        if len(profiles) >= 3:
            if family != "generic_multi_field_confirmation":
                return result(
                    "REJECT", -30, labels, reasons=(
                        "该模板只支持两个字段，不能把三条槽位压成 pair 关系",
                    )
                )
            concepts = {item.get("concept") for item in traits}
            analyst_confirmation = (
                "analyst_revision" in concepts
                and "analyst_dispersion" in concepts
                and any(
                    item.get("concept") == "sentiment"
                    and "analyst" in (item.get("tags") or [])
                    for item in traits
                )
            )
            if analyst_confirmation and frequency["status"] == "COMPATIBLE":
                return result(
                    "ALLOW", 80, labels,
                    "analyst_expectation_update",
                    symmetric=True,
                    preferred={
                        "data_field": "EITHER", "s": "EITHER", "t": "EITHER",
                    },
                    assignment_reason="三条字段共同表达分析师预期更新、离散与推荐变化",
                    evidence_strength="HIGH",
                    confirmation_mechanism="analyst_expectation_update",
                    reasons=("三条 leg 映射到同一 analyst expectation update mechanism",),
                )
            return result(
                "REVIEW", 0, labels,
                "unknown_confirmation",
                symmetric=True,
                reasons=("pair edges do not prove one shared confirmation mechanism",),
            )

        relationship_type = cls._relationship_type(labels)
        preferred = {"p": "EITHER", "s": "EITHER"}
        symmetric = True
        assignment_reason = "relationship is symmetric under this template contract"
        if frequency["status"] == "INCOMPATIBLE":
            return result(
                "REJECT", -40, labels, relationship_type,
                reasons=("frequency incompatibility blocks this relationship",),
            )
        if family in {"relationship_spread", "relative_spread_change", "generic_multi_field_spread"}:
            if relationship_type == "same_economic_concept":
                if traits[0].get("measurement") != traits[1].get("measurement"):
                    return result(
                        "REJECT", -30, labels, relationship_type,
                        reasons=("same concept has incompatible level/change measurements",),
                    )
            allowed = {"same_economic_concept", "option_pair", "revision_dispersion"}
            if relationship_type not in allowed:
                return result(
                    "REJECT", -30, labels, relationship_type,
                    reasons=("spread requires comparable quantities or an explicit differential",),
                )
        elif family in {"relative_ratio", "generic_multi_field_ratio"}:
            if relationship_type == "option_pair":
                preferred = {"p": "EITHER", "s": "EITHER"}
                symmetric = True
                assignment_reason = "put/call implied volatility pair is symmetric for ratio testing"
            elif relationship_type == "numerator_denominator":
                if not (
                    traits[0].get("concept") == "earnings"
                    and traits[1].get("concept") == "fundamental"
                ):
                    return result(
                        "REJECT", -35, labels, relationship_type,
                        reasons=("ratio direction is only proven for earnings over assets",),
                    )
                preferred = {"p": "numerator", "s": "denominator"}
                symmetric = False
                assignment_reason = "earnings is the numerator and assets is the scale denominator"
            else:
                return result(
                    "REJECT", -30, labels, relationship_type,
                    reasons=("ratio requires a directional numerator/denominator or put/call pair",),
                )
        elif family in {"relative_covariance", "relative_correlation"}:
            allowed = {
                "same_economic_concept", "option_pair", "revision_dispersion",
                "price_volume", "complementary_expectations",
            }
            if relationship_type not in allowed:
                return result(
                    "REJECT", -30, labels, relationship_type,
                    reasons=("co-movement requires a shared or explicitly complementary mechanism",),
                )
        else:
            return result(
                "REJECT", -30, labels, relationship_type,
                reasons=("no relationship contract is defined for this template family",),
            )

        if frequency["status"] == "REVIEW":
            return result(
                "REVIEW", 20, labels, relationship_type,
                symmetric=symmetric,
                preferred=preferred,
                assignment_reason=assignment_reason,
                reasons=("frequency compatibility is REVIEW; auto Factory cannot use it",),
            )
        if family in {"relative_ratio", "generic_multi_field_ratio"}:
            return result(
                "ALLOW", 70 if relationship_type == "numerator_denominator" else 60,
                labels, relationship_type,
                symmetric=symmetric,
                preferred=preferred,
                assignment_reason=assignment_reason,
                evidence_strength="HIGH",
                reasons=("directional ratio contract passed",),
            )
        return result(
            "ALLOW", 60, labels, relationship_type,
            symmetric=True,
            preferred={"p": "EITHER", "s": "EITHER"},
            assignment_reason="relationship is symmetric under this template contract",
            evidence_strength="HIGH" if relationship_type in {"option_pair", "revision_dispersion"} else "MEDIUM",
            reasons=("template-specific relationship contract passed",),
        )

    def rank_compatible_templates(self, profile, templates=None):
        """Rank a small, deterministic view of templates for one field."""
        templates = list(templates or self.registry.economic_templates())
        ranked = []
        for template in templates:
            compatibility = self._template_semantic_compatibility(template, profile)
            if compatibility["admission"] == "REJECT":
                continue
            if len(template.required_slots) > 1:
                compatibility = dict(compatibility)
                compatibility["admission"] = "REVIEW"
                compatibility["score"] -= 5
                compatibility["reasons"] = list(compatibility["reasons"]) + [
                    "多字段关系需在实际伴侣字段上复核"
                ]
            ranked.append({"template": template, **compatibility})
        ranked.sort(key=lambda item: (-item["score"], item["template"].template_id))
        return ranked

    @staticmethod
    def _field_mechanism(profile, traits, template, relation=None):
        field_id = str(profile.get("id"))
        if traits.get("semantic_admission") != "ALLOW":
            return (
                f"字段 {field_id} 的语义准入为 {traits.get('semantic_admission', 'UNKNOWN')}；"
                f"当前 profile 只能支持 {template.family} 的语法审阅，不能证明该字段具备该经济机制。"
            )
        fit_reason = {
            "analyst_revision": "修正值直接承载分析师预期更新，适合检验变化、持续性或滞后确认",
            "option_relative": "put-call/skew 字段表达期权分布的相对位置，适合离散或相对关系检验",
            "liquidity": "交易活跃度或未平仓量描述参与程度，适合流动性与活动强度检验",
            "volatility": "波动率是风险暴露或状态变量，适合风险调整、regime 或相对关系",
            "fundamental": "低频基本面水平代表经济规模，适合持久性和相对状态检验",
            "earnings": "盈利相关字段承载经营预期，适合变化与信息扩散检验",
            "event_count": "事件计数代表注意力事件强度，适合事件发生后的变化检验",
            "data_quality": "数据质量字段描述可用性风险，只进入缺失或陈旧信息机制",
        }.get(
            traits["concept"],
            f"该字段的 {traits['measurement']} 测量与 {template.family} 的有限结构相容",
        )
        mechanism = (
            f"字段 {field_id} 被识别为 {traits['concept']}，测量为 {traits['measurement']}，"
            f"频率为 {traits['frequency']}，符号语义为 {traits['sign_semantics']}，"
            f"行为为 {traits['behavior']}；{fit_reason}。"
            "该机制仍需用独立样本和平台 checks 证伪。"
        )
        if relation and relation.get("labels"):
            mechanism += f" 槽位关系证据为：{', '.join(relation['labels'])}。"
        return mechanism

    def _select_companion_profiles(self, fields, primary, required_count, offset,
                                   template=None):
        """Select distinct, type-compatible companion fields for generic slots.

        When the discovery pool contains multiple datasets, prefer companions
        from another dataset.  If no compatible cross-dataset field exists,
        fall back to the same dataset only when that is the sole viable pool;
        this records a truthful limitation instead of silently pretending the
        batch is cross-dataset.
        """
        if required_count <= 0:
            return []
        primary_key = self._profile_key(primary)
        primary_id = str(primary.get("id"))
        primary_type = str(primary.get("type") or "").upper()
        primary_traits = _derive_field_semantic_traits(primary)
        candidates = []
        for candidate in list(fields[offset + 1:]) + list(fields[:offset]):
            if not isinstance(candidate, dict) or not candidate.get("id"):
                continue
            candidate_id = str(candidate.get("id"))
            if candidate_id == primary_id or self._profile_key(candidate) == primary_key:
                continue
            if not isinstance(candidate.get("description"), str) or not candidate["description"].strip():
                continue
            if str(candidate.get("semantic_status", "UNKNOWN")).upper() == "UNKNOWN":
                continue
            if template is not None:
                candidate_traits = _derive_field_semantic_traits(candidate)
                if template.family == "generic_multi_field_confirmation":
                    analyst_family = {
                        "analyst_revision", "analyst_dispersion", "sentiment",
                    }
                    frequency = self._frequency_compatibility(
                        [primary_traits, candidate_traits], template.family
                    )
                    relation = {
                        "admission": (
                            "ALLOW"
                            if {
                                primary_traits.get("concept"),
                                candidate_traits.get("concept"),
                            } <= analyst_family
                            and frequency["status"] == "COMPATIBLE"
                            else "REJECT"
                        ),
                        "score": 40,
                        "labels": [],
                    }
                else:
                    relation = self._relationship_gate([primary, candidate], template)
                if relation["admission"] != "ALLOW":
                    continue
            candidate_type = str(candidate.get("type") or "").upper()
            if primary_type and candidate_type and candidate_type != primary_type:
                continue
            if any(candidate_id == str(item[1].get("id")) for item in candidates):
                continue
            if template is None:
                relation = {"admission": "REVIEW", "score": 0, "labels": []}
            candidates.append((relation, candidate))
        dataset_ids = {
            self._profile_dataset(item) for item in fields
            if isinstance(item, dict) and item.get("id")
        }
        if len(dataset_ids) > 1:
            cross_dataset = [
                item for item in candidates
                if self._profile_dataset(item[1]) != self._profile_dataset(primary)
            ]
            if cross_dataset:
                candidates = cross_dataset + [
                    item for item in candidates if item not in cross_dataset
                ]
        candidates.sort(
            key=lambda item: (
                0 if item[0].get("admission") == "ALLOW" else 1,
                0 if self._profile_dataset(item[1]) != self._profile_dataset(primary) else 1,
                -int(item[0].get("score", 0)),
                str(item[1].get("id")),
            )
        )
        return [item[1] for item in candidates[:required_count]]

    def screen_optimization_parents(self, parents, *, excluded_expressions=None,
                                    min_sharpe=0.9, min_fitness=0.6,
                                    min_turnover=0.01, max_turnover=0.7):
        """Apply deterministic code gates before Agent semantic selection.

        This gate only examines observable evidence and anti-budget signals.
        The lightweight cloud Alpha feed can prioritize or deduplicate a
        parent, but it cannot become performance evidence by itself.
        """
        if not isinstance(parents, (list, tuple)):
            return []
        try:
            min_sharpe, min_fitness = float(min_sharpe), float(min_fitness)
            min_turnover, max_turnover = float(min_turnover), float(max_turnover)
        except (TypeError, ValueError):
            return []
        excluded = {
            canonical_expression(value)
            for value in (excluded_expressions or [])
            if isinstance(value, str) and value.strip()
        }
        screened = []
        seen = set()
        for parent in parents:
            if not isinstance(parent, dict):
                continue
            if str(parent.get("status") or "").upper() != "DONE":
                continue
            expression = parent.get("expression")
            if not isinstance(expression, str) or not expression.strip():
                continue
            identity = canonical_expression(expression)
            if not identity or identity in seen or identity in excluded:
                continue
            metrics = parent.get("metrics")
            if not isinstance(metrics, dict):
                continue
            try:
                sharpe = float(metrics.get("sharpe"))
                fitness = float(metrics.get("fitness"))
                turnover = float(metrics.get("turnover"))
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in (sharpe, fitness, turnover)):
                continue
            if not ((sharpe >= min_sharpe or fitness >= min_fitness)
                    and min_turnover <= turnover <= max_turnover):
                continue
            if isinstance(parent.get("health"), dict) and not parent["health"].get("ok"):
                continue
            if not parent.get("fields_used") or not parent.get("datasets"):
                continue
            required_metadata = (
                "field_understanding", "field_analysis", "field_source",
                "field_hypothesis_basis",
            )
            if any(not parent.get(key) for key in required_metadata):
                continue
            seen.add(identity)
            screened.append(parent)
        return screened

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
        parents = self.screen_optimization_parents(
            parents,
            excluded_expressions=excluded_expressions,
            min_sharpe=min_sharpe,
            min_fitness=min_fitness,
            min_turnover=min_turnover,
            max_turnover=max_turnover,
        )
        out = []
        seen_parents = set()
        for parent in parents:
            if len(out) >= limit or not isinstance(parent, dict):
                break
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
            if identity in seen_parents:
                continue
            seen_parents.add(identity)
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
            child = parent.get("child_economic_hypothesis") or {}
            if not isinstance(child, dict):
                continue
            child_expression = child.get("expression")
            child_mechanism = child.get("economic_mechanism")
            child_change = child.get("change_type")
            if not all(isinstance(value, str) and value.strip() for value in (
                child_expression, child_mechanism, child_change
            )):
                continue
            if parameter_only_change_reason(base, child_expression):
                continue
            if overfit_expression_reason(child_expression):
                continue
            variants = ((child_change, child_expression, child_mechanism),)
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
                    "experiment_question": child.get(
                        "experiment_question",
                        f"新的经济机制 {change_type} 是否在独立证据上改善净收益与稳定性？",
                    ),
                    "expected_failure_modes": [
                        "平滑过度导致信号衰减或延迟",
                        "优化后换手、相关性或健康检查恶化",
                    ],
                    "tuning_risk": bool(child.get("tuning_risk", False)),
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
                    "rationale": child.get("rationale") or rationale,
                    "direction": parent.get("direction") or "long",
                    "expected_horizon": parent.get("expected_horizon") or "short-term",
                    "falsification": child.get(
                        "falsification",
                        "若独立样本、健康检查或自相关证据恶化，则关闭该优化分支。",
                    ),
                    "direction_transform": child.get(
                        "direction_transform",
                        {
                            "applied": False,
                            "reason": "沿用 parent 的方向，不把方向翻转当作新机制。",
                        },
                    ),
                    "self_correlation_impact": child.get(
                        "self_correlation_impact",
                        {
                            "expected_effect": "UNKNOWN",
                            "basis": "pre_simulation_structural_forecast",
                            "rationale": "优化前没有平台结算序列，不把结构差异冒充为低自相关。",
                            "admission": "REVIEW",
                        },
                    ),
                })
                proposal["proposal_origin"] = "agent_optimizer"
                proposal["research_layer"] = "optimization"
                proposal["optimization_source"] = parent.get(
                    "optimization_source", "current_run"
                )
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
        explicit_templates = self.registry.select(hypothesis)
        has_explicit_templates = bool(
            hypothesis.get("template_ids") or hypothesis.get("template_family")
            or (isinstance(hypothesis.get("template_ref"), dict)
                and hypothesis.get("template_ref"))
        )
        template_order = (
            [template.template_id for template in explicit_templates]
            if has_explicit_templates else (
                [template.template_id for template in self.registry.economic_templates()]
                if economic_mode else [
                    "rank_level", "zscore_level", "reversal_zscore_20",
                    "momentum_mean_20", "change_delta_5", "vector_mean_rank",
                ]
            )
        )
        if not template_order:
            return []
        template_catalog = [
            self.registry.get(template_id)
            for template_id in template_order
        ]
        template_catalog = [template for template in template_catalog if template]
        if not template_catalog:
            return []
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
            primary_key = self._profile_key(profile)
            if primary_key in used_fields:
                continue
            selected = None
            traits = _derive_field_semantic_traits(profile)
            compatible_templates = []
            for template in template_catalog:
                compatibility = self._template_semantic_compatibility(
                    template, profile, traits
                )
                if compatibility["admission"] != "REJECT":
                    compatible_templates.append((template, compatibility))
            # Explore only the compatible semantic neighborhood.  Sorting by
            # fit first preserves deterministic, field-aware preference while
            # the offset rotates ties and still allows structural exploration.
            compatible_templates.sort(
                key=lambda item: (-item[1]["score"], item[0].template_id)
            )
            for step in range(len(compatible_templates)):
                template, compatibility = compatible_templates[
                    (offset + step) % len(compatible_templates)
                ]
                template_id = template.template_id
                family_cap = 4 if economic_mode else MAX_TEMPLATE_FAMILY_PER_BATCH
                if family_counts.get(template.family, 0) >= family_cap:
                    continue
                companion_slots = [
                    slot for slot in template.required_slots
                    if slot not in {"p", "data_field"}
                ]
                slot_profiles = [profile]
                slot_profiles.extend(self._select_companion_profiles(
                    fields, profile, len(companion_slots), offset, template
                ))
                if len(slot_profiles) != len(companion_slots) + 1:
                    continue
                relation = None
                if companion_slots:
                    relation = self._relationship_gate(slot_profiles, template)
                    if relation["admission"] != "ALLOW":
                        continue
                generated = self.generate(
                    dict(hypothesis, template_ids=[template_id]),
                    slot_profiles,
                    count=1,
                )
                if not generated:
                    continue
                generated_candidate = generated[0]
                generated_expression = generated_candidate["expression"]
                if (
                    field_type != "VECTOR"
                    and {"vec_avg", "vec_sum"}.intersection(
                        analyze_expression(generated_expression).operators
                    )
                ):
                    continue
                if canonical_expression(generated_expression) in excluded:
                    continue
                actual_ops = list(analyze_expression(generated_expression).operators)
                if not set(actual_ops).issubset(operators):
                    continue
                selected = (
                    template, generated_candidate, actual_ops, slot_profiles,
                    compatibility, relation,
                )
                break
            if selected is None:
                continue
            template, candidate, actual_ops, slot_profiles, compatibility, relation = selected
            field_source = profile.get("field_source") or source_default
            if not isinstance(field_source, dict):
                field_source = {"kind": "unknown", "path": None, "snapshot_date": None}
            profile_by_id = {
                str(item.get("id")): item
                for item in slot_profiles
                if isinstance(item, dict) and item.get("id") is not None
            }
            profile_by_key = {
                self._profile_key(item): item for item in slot_profiles
                if isinstance(item, dict) and item.get("id") is not None
            }
            used_field_ids = [
                str(item) for item in (candidate.get("fields_used") or [field_id])
                if str(item) in profile_by_id
            ]
            if not used_field_ids:
                continue
            used_profiles = []
            for field_ref in candidate.get("field_refs") or []:
                if not isinstance(field_ref, dict) or not field_ref.get("id"):
                    continue
                key = (
                    str(field_ref.get("dataset")) if field_ref.get("dataset") is not None else None,
                    str(field_ref.get("id")),
                )
                profile = profile_by_key.get(key) or profile_by_id.get(str(field_ref["id"]))
                if profile is not None and profile not in used_profiles:
                    used_profiles.append(profile)
            if not used_profiles:
                used_profiles = [profile_by_id[item] for item in used_field_ids]
            used_field_ids = [str(item.get("id")) for item in used_profiles]
            field_understanding = {
                item: f"基于本轮 discovery 原文：{profile_by_id[item].get('description')}"
                for item in used_field_ids
            }
            field_analysis = {
                item: {
                    "semantic": profile_by_id[item].get("description"),
                    "coverage": profile_by_id[item].get("coverage"),
                    "frequency": profile_by_id[item].get("frequency"),
                    "data_type": profile_by_id[item].get("type"),
                    "semantic_traits": _derive_field_semantic_traits(
                        profile_by_id[item]
                    ),
                }
                for item in used_field_ids
            }
            mechanisms = {
                item: self._field_mechanism(
                    profile_by_id[item],
                    _derive_field_semantic_traits(profile_by_id[item]),
                    template,
                    relation,
                )
                for item in used_field_ids
            }
            field_hypothesis_basis = {
                item: {
                    "description": profile_by_id[item].get("description"),
                    "mechanism": mechanisms[item],
                    "semantic_traits": _derive_field_semantic_traits(
                        profile_by_id[item]
                    ),
                    "independent_increment": "该 BASELINE 只检验这些字段组合的独立增量信息。",
                    "direction": "reversal" if "reversal" in template.family else "long",
                }
                for item in used_field_ids
            }
            datasets = []
            for item in used_profiles:
                dataset = item.get("dataset")
                if dataset and dataset not in datasets:
                    datasets.append(dataset)
            proposal = {
                "expression": candidate["expression"],
                "fields": used_field_ids,
                "field_refs": list(candidate.get("field_refs") or []),
                "datasets": datasets,
                "field_understanding": field_understanding,
                "field_analysis": field_analysis,
                "field_source": field_source,
                "field_hypothesis_basis": field_hypothesis_basis,
                "economic_mechanism": mechanisms[used_field_ids[0]],
                "semantic_admission": (
                    relation["admission"] if relation else compatibility["admission"]
                ),
                "direction_transform": {
                    **candidate["direction_transform"],
                    "reason": mechanisms[used_field_ids[0]],
                },
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
                # Budget arms distinguish an economic template applied to
                # different verified fields.  This permits breadth in the
                # 100-slot factory batch without treating one field's
                # numeric tuning as a new arm.
                "mechanism_family": f"{template.family}:{field_id}",
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
                            "relationship_audit", "factory_version")
            })
            proposal["proposal_origin"] = "factory"
            assembled.append(proposal)
            excluded.add(canonical_expression(proposal["expression"]))
            used_fields.add(primary_key)
            family_counts[template.family] = family_counts.get(template.family, 0) + 1
            if len(assembled) >= limit:
                break
        return assembled

    def generate_factory_batch(self, hypothesis, fields, operator_reference,
                               target=100, optimized=(),
                               excluded_expressions=None, seed=None):
        """Generate one large, structurally diverse factory batch.

        The factory owns breadth.  It cycles verified field profiles through
        the bounded economic template catalog; it does not scan arbitrary
        windows, weights, signs, or other numeric parameters.  Optimizer
        proposals are accepted as a separately marked prefix so the caller
        can retain provenance while the factory still owns the 100-slot
        envelope.
        """
        try:
            limit = max(0, int(target))
        except (TypeError, ValueError):
            return []
        if limit <= 0 or not isinstance(fields, list):
            return []
        result = []
        seen_slot_scopes = {
            (
                proposal.get("template_id"),
                tuple(sorted(str(field) for field in proposal.get("fields", []))),
            )
            for proposal in (optimized or ())
            if isinstance(proposal, dict)
        }
        excluded = {
            canonical_expression(value)
            for value in (excluded_expressions or [])
            if isinstance(value, str) and value.strip()
        }
        for proposal in optimized or ():
            if not isinstance(proposal, dict):
                continue
            expression = proposal.get("expression")
            if not isinstance(expression, str) or not expression.strip():
                continue
            fields_used = proposal.get("fields") or proposal.get("fields_used") or []
            if isinstance(fields_used, (list, tuple)) and len(fields_used) > 1:
                relationship_audit = proposal.get("relationship_audit") or {}
                admission = str(
                    proposal.get("relationship_admission")
                    or relationship_audit.get("relationship_admission")
                    or ""
                ).upper()
                if admission != "ALLOW":
                    continue
            identity = canonical_expression(expression)
            if identity in excluded:
                continue
            item = dict(proposal)
            item.setdefault("proposal_origin", "agent_optimizer")
            item.setdefault("research_layer", "optimization")
            result.append(item)
            excluded.add(identity)
            if len(result) >= limit:
                return result[:limit]

        templates = list(self.registry.economic_templates())
        if not templates:
            return result
        verified = [
            field for field in fields
            if isinstance(field, dict)
            and isinstance(field.get("id"), (str, int))
            and isinstance(field.get("description"), str)
            and field.get("description", "").strip()
            and str(field.get("semantic_status", "UNKNOWN")).upper() != "UNKNOWN"
        ]
        # Explore field order, but derive template order from each field's
        # semantic compatibility.  Only a small top-ranked pool is explored;
        # the full catalog is never treated as an interchangeable shuffle.
        rng = random.Random(
            str(seed if seed is not None else hypothesis.get("id", "factory"))
        )
        rng.shuffle(verified)
        for offset, profile in enumerate(verified):
            if len(result) >= limit:
                break
            ranked = self.rank_compatible_templates(profile, templates)
            if not ranked:
                continue
            top_score = ranked[0]["score"]
            high_score_pool = [
                item for item in ranked
                if item["score"] == top_score
            ]
            lower_score_pool = [
                item for item in ranked
                if item["score"] < top_score
            ][:7]
            relationship_pool = [
                item for item in ranked
                if len(item["template"].required_slots) > 1
            ][:6]
            rng.shuffle(high_score_pool)
            rng.shuffle(lower_score_pool)
            rng.shuffle(relationship_pool)
            pool = []
            for item in high_score_pool + lower_score_pool + relationship_pool:
                if item not in pool:
                    pool.append(item)
            for ranked_template in pool:
                if len(result) >= limit:
                    break
                template = ranked_template["template"]
                # Pair templates require a semantically reviewed secondary
                # field.  The normal assemble path remains the single source
                # of proposal metadata and operator evidence.
                companion_slots = [
                    slot for slot in template.required_slots
                    if slot not in {"p", "data_field"}
                ]
                if companion_slots:
                    # Give assemble_proposals the full rotated pool so its
                    # cross-dataset preference is real.  Passing a preselected
                    # same-dataset pair here would make that safety rule
                    # impossible to enforce.
                    slots = [profile] + verified[offset + 1:] + verified[:offset]
                else:
                    slots = [profile]
                generated = self.assemble_proposals(
                    dict(hypothesis, template_mode="economic",
                         template_ids=[template.template_id]),
                    slots, operator_reference, max_candidates=1,
                    excluded_expressions=excluded,
                )
                if not generated:
                    continue
                proposal = generated[0]
                slot_scope = (
                    proposal.get("template_id"),
                    tuple(sorted(str(field) for field in proposal.get("fields", []))),
                )
                if slot_scope in seen_slot_scopes:
                    continue
                seen_slot_scopes.add(slot_scope)
                proposal["proposal_origin"] = "factory"
                proposal["research_layer"] = "exploration"
                proposal["exploration_objective"] = "signal_discovery"
                proposal["research_role"] = "EXPLORE"
                proposal["experiment_stage"] = "BASELINE"
                result.append(proposal)
                excluded.add(canonical_expression(proposal["expression"]))
        return result[:limit]
