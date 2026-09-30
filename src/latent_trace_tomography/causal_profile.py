from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any, NamedTuple


SCHEMA_VERSION = "0.1.0"
ESTIMAND_KIND = "selected_site_intervention_susceptibility"
PROBABILITY_STATUS = "not_calibrated"
CLAIM_TIER = "named_dependency_cluster_engineering_pilot"
SITE_STABILITY_METHOD = "leave_one_content_seed_out_site_rediscovery_v1"
SITE_STABILITY_RESAMPLE_COUNT = 8
SITE_STABILITY_THRESHOLD = 0.75
INTERVAL_SCOPE = "within_target_measurement_precision"
INTERVAL_METHOD = "content_seed_delete_one_jackknife_normal_95_v1"
JACKKNIFE_DELETE_ONE_COUNT = 16
NORMAL_95_Z = 1.959963984540054
PRIMARY_INDEPENDENT_UNIT = "dependency_cluster_id"
MATCHED_NULL_KIND = "norm_matched_rotation"
MINIMUM_ROUTE_SPECIFIC_IIA = 0.25
MINIMUM_SELF_SHAM_ACCURACY = 0.90
MAXIMUM_ABSOLUTE_CONTROL_SITE_SPECIFIC = 0.10
MINIMUM_CODEBOOK_COMPETENCE_ACCURACY = 0.90
MINIMUM_SITE_SELECTION_FREQUENCY = SITE_STABILITY_THRESHOLD
ARITHMETIC_TOLERANCE = 1e-9
CAUSAL_LABEL_CONTENT_SEED_COUNT = 16
PRIMARY_PAIRS_PER_CONTENT_SEED_PER_COMPONENT = 4
CAUSAL_COMPONENT_TRIAL_COUNT = (
    CAUSAL_LABEL_CONTENT_SEED_COUNT * PRIMARY_PAIRS_PER_CONTENT_SEED_PER_COMPONENT
)
CAUSAL_COMPONENT_DELETE_ONE_TRIAL_COUNT = (
    CAUSAL_COMPONENT_TRIAL_COUNT - PRIMARY_PAIRS_PER_CONTENT_SEED_PER_COMPONENT
)
CODEBOOK_COMPETENCE_TRIAL_COUNT = CAUSAL_LABEL_CONTENT_SEED_COUNT * 8

CAUSAL_VARIABLES = (
    "semantic_solution",
    "surface_cue",
    "answer_codebook",
)

ANCHOR_ROUTE_COMPONENTS = {
    "semantic_anchor": ("semantic_solution",),
    "surface_cue_anchor": ("surface_cue",),
    "mixed_anchor": ("semantic_solution", "surface_cue"),
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CausalProfileError(ValueError):
    """Raised when an OSS causal-profile record violates its scientific contract."""


class _EffectValidationResult(NamedTuple):
    specific_iia: float
    delete_one_by_id: dict[str, float]
    delete_one_trial_by_id: dict[str, int]
    intended_success_count: int
    matched_null_success_count: int
    self_sham_success_count: int
    control_site_success_count: int
    trial_count: int


class _CodebookValidationResult(NamedTuple):
    success_count: int
    trial_count: int


class _SiteStabilityValidationResult(NamedTuple):
    selected_counts: dict[str, int]
    omitted_content_seed_ids: frozenset[str]


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, context: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise CausalProfileError(f"{context} fields mismatch: missing={missing}, extra={extra}")


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CausalProfileError(f"{context} must be an object")
    return value


def _number(
    value: Any,
    *,
    context: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CausalProfileError(f"{context} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise CausalProfileError(f"{context} must be a finite number")
    if minimum is not None and result < minimum:
        raise CausalProfileError(f"{context} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise CausalProfileError(f"{context} must be at most {maximum}")
    return result


def _positive_int(value: Any, *, context: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise CausalProfileError(f"{context} must be an integer at least {minimum}")
    return value


def _nonempty_text(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise CausalProfileError(f"{context} must be non-empty text")
    return value


def _sha256(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise CausalProfileError(f"{context} must be a lowercase SHA-256 digest")
    return value


def _close(left: float, right: float, *, tolerance: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def delete_one_jackknife_interval(
    point_estimate: float,
    delete_one_estimates: tuple[float, ...],
    *,
    lower_bound: float,
    upper_bound: float,
) -> tuple[float, float]:
    """Return the frozen within-target 95 percent delete-one interval."""

    point = _number(point_estimate, context="point_estimate")
    lower = _number(lower_bound, context="lower_bound")
    upper = _number(upper_bound, context="upper_bound")
    if lower > upper:
        raise ValueError("lower_bound must not exceed upper_bound")
    if not lower <= point <= upper:
        raise ValueError("point_estimate must lie within the supplied bounds")
    if len(delete_one_estimates) != JACKKNIFE_DELETE_ONE_COUNT:
        raise ValueError("exactly 16 delete-one content-seed estimates are required")
    estimates = tuple(
        _number(value, context=f"delete_one_estimates[{index}]")
        for index, value in enumerate(delete_one_estimates)
    )
    mean = math.fsum(estimates) / JACKKNIFE_DELETE_ONE_COUNT
    variance_sum = math.fsum((value - mean) ** 2 for value in estimates)
    standard_error = math.sqrt(
        (JACKKNIFE_DELETE_ONE_COUNT - 1) / JACKKNIFE_DELETE_ONE_COUNT * variance_sum
    )
    return (
        max(lower, point - NORMAL_95_Z * standard_error),
        min(upper, point + NORMAL_95_Z * standard_error),
    )


def _validate_interval(
    *,
    value: float,
    lower: Any,
    upper: Any,
    context: str,
    minimum: float,
    maximum: float,
    tolerance: float,
) -> tuple[float, float]:
    lower_value = _number(lower, context=f"{context}.ci95_lower", minimum=minimum, maximum=maximum)
    upper_value = _number(upper, context=f"{context}.ci95_upper", minimum=minimum, maximum=maximum)
    if lower_value > upper_value:
        raise CausalProfileError(f"{context} interval lower bound exceeds upper bound")
    if value < lower_value - tolerance or value > upper_value + tolerance:
        raise CausalProfileError(f"{context} interval does not contain its point estimate")
    return lower_value, upper_value


def _validate_specificity_controls(
    value: Any,
    *,
    context: str,
    full_trial_count: int,
    matched_null_iia: float,
    tolerance: float,
) -> tuple[int, int]:
    controls = _mapping(value, context=context)
    _exact_keys(controls, {"self_sham", "control_site_delta"}, context=context)

    self_sham_context = f"{context}.self_sham"
    self_sham = _mapping(controls["self_sham"], context=self_sham_context)
    _exact_keys(
        self_sham,
        {"success_count", "trial_count", "accuracy"},
        context=self_sham_context,
    )
    self_sham_trial_count = _positive_int(
        self_sham["trial_count"], context=f"{self_sham_context}.trial_count"
    )
    if self_sham_trial_count != full_trial_count:
        raise CausalProfileError(
            f"{self_sham_context}.trial_count must equal the component trial_count"
        )
    self_sham_success_count = _positive_int(
        self_sham["success_count"],
        context=f"{self_sham_context}.success_count",
        minimum=0,
    )
    if self_sham_success_count > self_sham_trial_count:
        raise CausalProfileError(f"{self_sham_context}.success_count must not exceed trial_count")
    self_sham_accuracy = _number(
        self_sham["accuracy"],
        context=f"{self_sham_context}.accuracy",
        minimum=0,
        maximum=1,
    )
    if not _close(
        self_sham_accuracy,
        self_sham_success_count / self_sham_trial_count,
        tolerance=tolerance,
    ):
        raise CausalProfileError(
            f"{self_sham_context}.accuracy must equal success_count / trial_count"
        )

    control_context = f"{context}.control_site_delta"
    control_site = _mapping(controls["control_site_delta"], context=control_context)
    _exact_keys(
        control_site,
        {"success_count", "trial_count", "iia", "specific_vs_matched_null"},
        context=control_context,
    )
    control_trial_count = _positive_int(
        control_site["trial_count"], context=f"{control_context}.trial_count"
    )
    if control_trial_count != full_trial_count:
        raise CausalProfileError(
            f"{control_context}.trial_count must equal the component trial_count"
        )
    control_success_count = _positive_int(
        control_site["success_count"],
        context=f"{control_context}.success_count",
        minimum=0,
    )
    if control_success_count > control_trial_count:
        raise CausalProfileError(f"{control_context}.success_count must not exceed trial_count")
    control_iia = _number(
        control_site["iia"], context=f"{control_context}.iia", minimum=0, maximum=1
    )
    if not _close(
        control_iia,
        control_success_count / control_trial_count,
        tolerance=tolerance,
    ):
        raise CausalProfileError(f"{control_context}.iia must equal success_count / trial_count")
    control_specific = _number(
        control_site["specific_vs_matched_null"],
        context=f"{control_context}.specific_vs_matched_null",
        minimum=-1,
        maximum=1,
    )
    if not _close(
        control_specific,
        control_iia - matched_null_iia,
        tolerance=tolerance,
    ):
        raise CausalProfileError(
            f"{control_context}.specific_vs_matched_null must equal iia - matched_null_iia"
        )
    return self_sham_success_count, control_success_count


def _validate_effect(
    effect: Any,
    *,
    context: str,
    tolerance: float,
) -> _EffectValidationResult:
    record = _mapping(effect, context=context)
    _exact_keys(
        record,
        {
            "intended_success_count",
            "matched_null_success_count",
            "intended_iia",
            "matched_null_iia",
            "matched_null_kind",
            "specific_iia",
            "specificity_controls",
            "delete_one_records",
            "ci95_lower",
            "ci95_upper",
            "trial_count",
        },
        context=context,
    )
    if record["matched_null_kind"] != MATCHED_NULL_KIND:
        raise CausalProfileError(f"{context}.matched_null_kind must equal {MATCHED_NULL_KIND!r}")
    trial_count = _positive_int(record["trial_count"], context=f"{context}.trial_count")
    intended_success_count = _positive_int(
        record["intended_success_count"],
        context=f"{context}.intended_success_count",
        minimum=0,
    )
    matched_success_count = _positive_int(
        record["matched_null_success_count"],
        context=f"{context}.matched_null_success_count",
        minimum=0,
    )
    if intended_success_count > trial_count or matched_success_count > trial_count:
        raise CausalProfileError(f"{context} success counts must not exceed trial_count")
    if trial_count != CAUSAL_COMPONENT_TRIAL_COUNT:
        raise CausalProfileError(
            f"{context}.trial_count must equal the frozen D_causal_label denominator "
            f"of {CAUSAL_COMPONENT_TRIAL_COUNT}: 16 content seeds x 4 symmetric-primary "
            "pairs x one greedy replicate"
        )
    expected_delete_trial_count = CAUSAL_COMPONENT_DELETE_ONE_TRIAL_COUNT

    intended = _number(
        record["intended_iia"], context=f"{context}.intended_iia", minimum=0, maximum=1
    )
    matched = _number(
        record["matched_null_iia"],
        context=f"{context}.matched_null_iia",
        minimum=0,
        maximum=1,
    )
    expected_intended = intended_success_count / trial_count
    expected_matched = matched_success_count / trial_count
    if not _close(intended, expected_intended, tolerance=tolerance):
        raise CausalProfileError(
            f"{context}.intended_iia must equal intended_success_count / trial_count"
        )
    if not _close(matched, expected_matched, tolerance=tolerance):
        raise CausalProfileError(
            f"{context}.matched_null_iia must equal matched_null_success_count / trial_count"
        )
    specific = _number(
        record["specific_iia"], context=f"{context}.specific_iia", minimum=-1, maximum=1
    )
    expected_specific = intended - matched
    if not _close(specific, expected_specific, tolerance=tolerance):
        raise CausalProfileError(
            f"{context}.specific_iia must equal intended_iia - matched_null_iia"
        )
    self_sham_success_count, control_site_success_count = _validate_specificity_controls(
        record["specificity_controls"],
        context=f"{context}.specificity_controls",
        full_trial_count=trial_count,
        matched_null_iia=expected_matched,
        tolerance=tolerance,
    )
    delete_one_raw = record["delete_one_records"]
    if not isinstance(delete_one_raw, list) or len(delete_one_raw) != JACKKNIFE_DELETE_ONE_COUNT:
        raise CausalProfileError(f"{context}.delete_one_records must contain exactly 16 records")
    delete_one_by_id: dict[str, float] = {}
    delete_one_trial_by_id: dict[str, int] = {}
    delete_one_trial_total = 0
    delete_one_intended_success_total = 0
    delete_one_matched_success_total = 0
    for index, raw_delete_one in enumerate(delete_one_raw):
        delete_context = f"{context}.delete_one_records[{index}]"
        delete_record = _mapping(raw_delete_one, context=delete_context)
        _exact_keys(
            delete_record,
            {
                "omitted_content_seed_id",
                "intended_success_count",
                "matched_null_success_count",
                "trial_count",
                "intended_iia",
                "matched_null_iia",
                "specific_iia",
            },
            context=delete_context,
        )
        omitted_id = _nonempty_text(
            delete_record["omitted_content_seed_id"],
            context=f"{delete_context}.omitted_content_seed_id",
        )
        if omitted_id in delete_one_by_id:
            raise CausalProfileError(
                f"{context}.delete_one_records omitted_content_seed_id values must be unique"
            )
        delete_trial_count = _positive_int(
            delete_record["trial_count"], context=f"{delete_context}.trial_count"
        )
        delete_intended_success_count = _positive_int(
            delete_record["intended_success_count"],
            context=f"{delete_context}.intended_success_count",
            minimum=0,
        )
        delete_matched_success_count = _positive_int(
            delete_record["matched_null_success_count"],
            context=f"{delete_context}.matched_null_success_count",
            minimum=0,
        )
        if (
            delete_intended_success_count > delete_trial_count
            or delete_matched_success_count > delete_trial_count
        ):
            raise CausalProfileError(f"{delete_context} success counts must not exceed trial_count")
        if delete_trial_count >= trial_count:
            raise CausalProfileError(
                f"{delete_context}.trial_count must be strictly less than full trial_count"
            )
        if delete_trial_count != expected_delete_trial_count:
            raise CausalProfileError(
                f"{delete_context}.trial_count must equal the full trial_count minus one "
                "of 16 equally sized preplanned content-seed blocks"
            )
        if delete_intended_success_count > intended_success_count:
            raise CausalProfileError(
                f"{delete_context}.intended_success_count must not exceed the full count"
            )
        if delete_matched_success_count > matched_success_count:
            raise CausalProfileError(
                f"{delete_context}.matched_null_success_count must not exceed the full count"
            )
        omitted_trial_count = trial_count - delete_trial_count
        if intended_success_count - delete_intended_success_count > omitted_trial_count:
            raise CausalProfileError(
                f"{delete_context} omitted intended_success_count must not exceed "
                "omitted trial_count"
            )
        if matched_success_count - delete_matched_success_count > omitted_trial_count:
            raise CausalProfileError(
                f"{delete_context} omitted matched_null_success_count must not exceed "
                "omitted trial_count"
            )
        delete_intended = _number(
            delete_record["intended_iia"],
            context=f"{delete_context}.intended_iia",
            minimum=0,
            maximum=1,
        )
        delete_matched = _number(
            delete_record["matched_null_iia"],
            context=f"{delete_context}.matched_null_iia",
            minimum=0,
            maximum=1,
        )
        if not _close(
            delete_intended,
            delete_intended_success_count / delete_trial_count,
            tolerance=tolerance,
        ):
            raise CausalProfileError(
                f"{delete_context}.intended_iia must equal intended_success_count / trial_count"
            )
        if not _close(
            delete_matched,
            delete_matched_success_count / delete_trial_count,
            tolerance=tolerance,
        ):
            raise CausalProfileError(
                f"{delete_context}.matched_null_iia must equal "
                "matched_null_success_count / trial_count"
            )
        delete_specific = _number(
            delete_record["specific_iia"],
            context=f"{delete_context}.specific_iia",
            minimum=-1,
            maximum=1,
        )
        if not _close(
            delete_specific,
            delete_intended - delete_matched,
            tolerance=tolerance,
        ):
            raise CausalProfileError(
                f"{delete_context}.specific_iia must equal intended_iia - matched_null_iia"
            )
        delete_one_by_id[omitted_id] = delete_specific
        delete_one_trial_by_id[omitted_id] = delete_trial_count
        delete_one_trial_total += delete_trial_count
        delete_one_intended_success_total += delete_intended_success_count
        delete_one_matched_success_total += delete_matched_success_count

    closure_multiplier = JACKKNIFE_DELETE_ONE_COUNT - 1
    if delete_one_trial_total != closure_multiplier * trial_count:
        raise CausalProfileError(
            f"{context}.delete_one_records trial_count sum must equal 15 * full trial_count"
        )
    if delete_one_intended_success_total != closure_multiplier * intended_success_count:
        raise CausalProfileError(
            f"{context}.delete_one_records intended_success_count sum must equal "
            "15 * full intended_success_count"
        )
    if delete_one_matched_success_total != closure_multiplier * matched_success_count:
        raise CausalProfileError(
            f"{context}.delete_one_records matched_null_success_count sum must equal "
            "15 * full matched_null_success_count"
        )

    delete_one_values = tuple(delete_one_by_id.values())
    lower, upper = _validate_interval(
        value=specific,
        lower=record["ci95_lower"],
        upper=record["ci95_upper"],
        context=context,
        minimum=-1,
        maximum=1,
        tolerance=tolerance,
    )
    expected_lower, expected_upper = delete_one_jackknife_interval(
        specific,
        delete_one_values,
        lower_bound=-1,
        upper_bound=1,
    )
    if not _close(lower, expected_lower, tolerance=tolerance) or not _close(
        upper, expected_upper, tolerance=tolerance
    ):
        raise CausalProfileError(
            f"{context} interval must equal the frozen 16-delete-one jackknife interval"
        )
    return _EffectValidationResult(
        specific_iia=expected_specific,
        delete_one_by_id=delete_one_by_id,
        delete_one_trial_by_id=delete_one_trial_by_id,
        intended_success_count=intended_success_count,
        matched_null_success_count=matched_success_count,
        self_sham_success_count=self_sham_success_count,
        control_site_success_count=control_site_success_count,
        trial_count=trial_count,
    )


def _validate_codebook_competence(value: Any, *, tolerance: float) -> _CodebookValidationResult:
    context = "codebook_competence"
    record = _mapping(value, context=context)
    _exact_keys(
        record,
        {"success_count", "trial_count", "accuracy", "causal_label_case_set_sha256"},
        context=context,
    )
    trial_count = _positive_int(record["trial_count"], context=f"{context}.trial_count")
    if trial_count != CODEBOOK_COMPETENCE_TRIAL_COUNT:
        raise CausalProfileError(
            "codebook_competence.trial_count must equal the frozen complete "
            "D_causal_label denominator of 128: 16 content seeds x 8 factorial cells"
        )
    success_count = _positive_int(
        record["success_count"], context=f"{context}.success_count", minimum=0
    )
    if success_count > trial_count:
        raise CausalProfileError("codebook_competence.success_count must not exceed trial_count")
    accuracy = _number(record["accuracy"], context=f"{context}.accuracy", minimum=0, maximum=1)
    if not _close(accuracy, success_count / trial_count, tolerance=tolerance):
        raise CausalProfileError(
            "codebook_competence.accuracy must equal success_count / trial_count"
        )
    _sha256(
        record["causal_label_case_set_sha256"],
        context="codebook_competence.causal_label_case_set_sha256",
    )
    return _CodebookValidationResult(success_count=success_count, trial_count=trial_count)


def _validate_site_selection_stability(value: Any) -> _SiteStabilityValidationResult:
    record = _mapping(value, context="site_selection_stability")
    _exact_keys(
        record,
        {
            "method",
            "resample_count",
            "stability_threshold",
            "overall_status",
            "components",
        },
        context="site_selection_stability",
    )
    if record["method"] != SITE_STABILITY_METHOD:
        raise CausalProfileError(
            "site_selection_stability.method must use the frozen leave-one-seed-out rediscovery"
        )
    if record["resample_count"] != SITE_STABILITY_RESAMPLE_COUNT:
        raise CausalProfileError("site_selection_stability.resample_count must equal 8")
    threshold = _number(
        record["stability_threshold"],
        context="site_selection_stability.stability_threshold",
        minimum=0.5,
        maximum=1,
    )
    if not _close(threshold, SITE_STABILITY_THRESHOLD, tolerance=1e-12):
        raise CausalProfileError("site_selection_stability.stability_threshold must equal 0.75")
    components = _mapping(record["components"], context="site_selection_stability.components")
    _exact_keys(
        components,
        set(CAUSAL_VARIABLES),
        context="site_selection_stability.components",
    )
    selected_counts: dict[str, int] = {}
    omission_ids_by_component: dict[str, frozenset[str]] = {}
    for variable in CAUSAL_VARIABLES:
        context = f"site_selection_stability.components.{variable}"
        component = _mapping(components[variable], context=context)
        _exact_keys(
            component,
            {
                "selected_site_id",
                "candidate_site_count",
                "selection_frequency",
                "score_gap_to_runner_up",
                "leave_one_selections",
                "selection_histogram",
            },
            context=context,
        )
        selected_site_id = _nonempty_text(
            component["selected_site_id"], context=f"{context}.selected_site_id"
        )
        candidate_site_count = _positive_int(
            component["candidate_site_count"],
            context=f"{context}.candidate_site_count",
            minimum=2,
        )
        leave_one_raw = component["leave_one_selections"]
        if (
            not isinstance(leave_one_raw, list)
            or len(leave_one_raw) != SITE_STABILITY_RESAMPLE_COUNT
        ):
            raise CausalProfileError(
                f"{context}.leave_one_selections must contain exactly 8 records"
            )
        omitted_ids: set[str] = set()
        selected_sites: list[str] = []
        for index, raw_selection in enumerate(leave_one_raw):
            selection_context = f"{context}.leave_one_selections[{index}]"
            selection = _mapping(raw_selection, context=selection_context)
            _exact_keys(
                selection,
                {"omitted_content_seed_id", "selected_site_id"},
                context=selection_context,
            )
            omitted_id = _nonempty_text(
                selection["omitted_content_seed_id"],
                context=f"{selection_context}.omitted_content_seed_id",
            )
            if omitted_id in omitted_ids:
                raise CausalProfileError(
                    f"{context}.leave_one_selections omitted_content_seed_id values must be unique"
                )
            omitted_ids.add(omitted_id)
            selected_sites.append(
                _nonempty_text(
                    selection["selected_site_id"],
                    context=f"{selection_context}.selected_site_id",
                )
            )
        omission_ids_by_component[variable] = frozenset(omitted_ids)

        histogram_raw = component["selection_histogram"]
        if not isinstance(histogram_raw, list) or not histogram_raw:
            raise CausalProfileError(f"{context}.selection_histogram must be a non-empty array")
        serialized_histogram: dict[str, int] = {}
        for index, raw_bin in enumerate(histogram_raw):
            bin_context = f"{context}.selection_histogram[{index}]"
            histogram_bin = _mapping(raw_bin, context=bin_context)
            _exact_keys(histogram_bin, {"site_id", "count"}, context=bin_context)
            site_id = _nonempty_text(histogram_bin["site_id"], context=f"{bin_context}.site_id")
            if site_id in serialized_histogram:
                raise CausalProfileError(
                    f"{context}.selection_histogram site_id values must be unique"
                )
            serialized_histogram[site_id] = _positive_int(
                histogram_bin["count"], context=f"{bin_context}.count"
            )
        if sum(serialized_histogram.values()) != SITE_STABILITY_RESAMPLE_COUNT:
            raise CausalProfileError(f"{context}.selection_histogram counts must sum to 8")
        derived_histogram = dict(Counter(selected_sites))
        if serialized_histogram != derived_histogram:
            raise CausalProfileError(
                f"{context}.selection_histogram must exactly match leave_one_selections"
            )
        if len(serialized_histogram) > candidate_site_count:
            raise CausalProfileError(
                f"{context}.selection_histogram cannot exceed candidate_site_count"
            )

        frequency = _number(
            component["selection_frequency"],
            context=f"{context}.selection_frequency",
            minimum=0,
            maximum=1,
        )
        selected_count = serialized_histogram.get(selected_site_id, 0)
        expected_frequency = selected_count / len(selected_sites)
        if not _close(frequency, expected_frequency, tolerance=1e-9):
            raise CausalProfileError(
                f"{context}.selection_frequency must equal the full selected-site count / 8"
            )
        selected_counts[variable] = selected_count
        _number(
            component["score_gap_to_runner_up"],
            context=f"{context}.score_gap_to_runner_up",
            minimum=0,
        )

    expected_status = (
        "stable"
        if all(
            selected_count * 4 >= 3 * SITE_STABILITY_RESAMPLE_COUNT
            for selected_count in selected_counts.values()
        )
        else "unstable"
    )
    if record["overall_status"] != expected_status:
        raise CausalProfileError(
            "site_selection_stability.overall_status is inconsistent with component frequencies"
        )
    reference_omission_ids = omission_ids_by_component[CAUSAL_VARIABLES[0]]
    if any(
        omission_ids_by_component[variable] != reference_omission_ids
        for variable in CAUSAL_VARIABLES[1:]
    ):
        raise CausalProfileError(
            "site_selection_stability components must share the same omitted_content_seed_id set"
        )
    return _SiteStabilityValidationResult(
        selected_counts=selected_counts,
        omitted_content_seed_ids=reference_omission_ids,
    )


def _boolean(value: Any, *, context: str) -> bool:
    if type(value) is not bool:
        raise CausalProfileError(f"{context} must be boolean")
    return value


def _validate_gate_evaluation(
    value: Any,
    *,
    anchor_condition_id: str,
    component_results: Mapping[str, _EffectValidationResult],
    codebook_result: _CodebookValidationResult,
    stability_selected_counts: Mapping[str, int],
) -> None:
    context = "gate_evaluation"
    gate = _mapping(value, context=context)
    _exact_keys(
        gate,
        {
            "thresholds",
            "required_route_components",
            "components",
            "route_specificity_pass",
            "specificity_controls_pass",
            "codebook_competence_pass",
            "site_selection_stability_pass",
            "overall_pass",
            "overall_status",
            "anchor_eligibility",
        },
        context=context,
    )
    frozen_thresholds = {
        "minimum_route_specific_iia": MINIMUM_ROUTE_SPECIFIC_IIA,
        "minimum_self_sham_accuracy": MINIMUM_SELF_SHAM_ACCURACY,
        "maximum_absolute_control_site_specific": MAXIMUM_ABSOLUTE_CONTROL_SITE_SPECIFIC,
        "minimum_codebook_competence_accuracy": MINIMUM_CODEBOOK_COMPETENCE_ACCURACY,
        "minimum_site_selection_frequency": MINIMUM_SITE_SELECTION_FREQUENCY,
    }
    thresholds = _mapping(gate["thresholds"], context=f"{context}.thresholds")
    _exact_keys(thresholds, set(frozen_thresholds), context=f"{context}.thresholds")
    for field, expected in frozen_thresholds.items():
        observed = _number(thresholds[field], context=f"{context}.thresholds.{field}")
        if not _close(observed, expected, tolerance=1e-12):
            raise CausalProfileError(
                f"{context}.thresholds.{field} must equal the frozen threshold {expected}"
            )

    required_route_components = list(ANCHOR_ROUTE_COMPONENTS[anchor_condition_id])
    if gate["required_route_components"] != required_route_components:
        raise CausalProfileError(
            "gate_evaluation.required_route_components must match anchor_condition_id"
        )
    required_route_set = set(required_route_components)
    component_gates = _mapping(gate["components"], context=f"{context}.components")
    _exact_keys(component_gates, set(CAUSAL_VARIABLES), context=f"{context}.components")

    expected_component_gates: dict[str, dict[str, bool]] = {}
    for variable in CAUSAL_VARIABLES:
        result = component_results[variable]
        route_required = variable in required_route_set
        specific_iia_pass = (
            4 * (result.intended_success_count - result.matched_null_success_count)
            >= result.trial_count
        )
        self_sham_pass = 10 * result.self_sham_success_count >= 9 * result.trial_count
        control_site_pass = (
            10 * abs(result.control_site_success_count - result.matched_null_success_count)
            <= result.trial_count
        )
        site_stability_pass = (
            stability_selected_counts[variable] * 4 >= 3 * SITE_STABILITY_RESAMPLE_COUNT
        )
        component_pass = (
            (not route_required or specific_iia_pass)
            and self_sham_pass
            and control_site_pass
            and site_stability_pass
        )
        expected_component_gates[variable] = {
            "route_required": route_required,
            "specific_iia_pass": specific_iia_pass,
            "self_sham_pass": self_sham_pass,
            "control_site_pass": control_site_pass,
            "site_stability_pass": site_stability_pass,
            "component_pass": component_pass,
        }
        component_context = f"{context}.components.{variable}"
        serialized_component = _mapping(component_gates[variable], context=component_context)
        _exact_keys(
            serialized_component,
            set(expected_component_gates[variable]),
            context=component_context,
        )
        for field, expected in expected_component_gates[variable].items():
            observed = _boolean(serialized_component[field], context=f"{component_context}.{field}")
            if observed is not expected:
                raise CausalProfileError(
                    f"{component_context}.{field} is inconsistent with measured metrics"
                )

    expected_route_pass = all(
        expected_component_gates[variable]["specific_iia_pass"]
        for variable in required_route_components
    )
    expected_controls_pass = all(
        expected_component_gates[variable]["self_sham_pass"]
        and expected_component_gates[variable]["control_site_pass"]
        for variable in CAUSAL_VARIABLES
    )
    expected_codebook_pass = 10 * codebook_result.success_count >= 9 * codebook_result.trial_count
    expected_site_pass = all(
        expected_component_gates[variable]["site_stability_pass"] for variable in CAUSAL_VARIABLES
    )
    expected_overall_pass = (
        expected_route_pass
        and expected_controls_pass
        and expected_codebook_pass
        and expected_site_pass
    )
    expected_top_level = {
        "route_specificity_pass": expected_route_pass,
        "specificity_controls_pass": expected_controls_pass,
        "codebook_competence_pass": expected_codebook_pass,
        "site_selection_stability_pass": expected_site_pass,
        "overall_pass": expected_overall_pass,
    }
    for field, expected in expected_top_level.items():
        observed = _boolean(gate[field], context=f"{context}.{field}")
        if observed is not expected:
            raise CausalProfileError(f"{context}.{field} is inconsistent with measured metrics")
    expected_status = "pass" if expected_overall_pass else "fail"
    if gate["overall_status"] != expected_status:
        raise CausalProfileError("gate_evaluation.overall_status is inconsistent with overall_pass")
    expected_anchor_eligibility = "resolved" if expected_overall_pass else "unresolved"
    if gate["anchor_eligibility"] != expected_anchor_eligibility:
        raise CausalProfileError(
            "gate_evaluation.anchor_eligibility is inconsistent with overall_pass"
        )


def validate_causal_profile_record_non_authoritative(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one profile's local arithmetic without authenticating its ancestry.

    JSON Schema constrains the serialized shape; this validator additionally
    enforces arithmetic identities, interval containment, and the relationship
    between site-selection frequencies and the declared stability status.
    It deliberately rejects population-interval language for this per-target,
    engineering-pilot record.  This low-level function is intentionally named
    ``non_authoritative`` because digest-shaped caller fields are not evidence
    that the profile belongs to a frozen execution.  Production scoring must
    use :func:`validate_causal_profile` below.
    """

    record = _mapping(payload, context="causal profile")
    _exact_keys(
        record,
        {
            "schema_version",
            "estimand_kind",
            "claim_tier",
            "target_id",
            "family_id",
            "dependency_cluster_id",
            "training_lineage_id",
            "checkpoint_id",
            "anchor_condition_id",
            "profile",
            "delta_specific",
            "codebook_competence",
            "probability_status",
            "uncertainty_scope",
            "site_selection_stability",
            "gate_evaluation",
            "provenance",
        },
        context="causal profile",
    )
    constants = {
        "schema_version": SCHEMA_VERSION,
        "estimand_kind": ESTIMAND_KIND,
        "claim_tier": CLAIM_TIER,
        "probability_status": PROBABILITY_STATUS,
    }
    for field, expected in constants.items():
        if record[field] != expected:
            raise CausalProfileError(f"{field} must equal {expected!r}")
    for field in (
        "target_id",
        "family_id",
        "dependency_cluster_id",
        "training_lineage_id",
        "checkpoint_id",
    ):
        _nonempty_text(record[field], context=field)
    anchor_condition_id = record["anchor_condition_id"]
    if anchor_condition_id not in ANCHOR_ROUTE_COMPONENTS:
        raise CausalProfileError(
            "anchor_condition_id must be semantic_anchor, surface_cue_anchor, or mixed_anchor"
        )

    profile = _mapping(record["profile"], context="profile")
    _exact_keys(profile, set(CAUSAL_VARIABLES), context="profile")
    component_results = {
        variable: _validate_effect(
            profile[variable],
            context=f"profile.{variable}",
            tolerance=ARITHMETIC_TOLERANCE,
        )
        for variable in CAUSAL_VARIABLES
    }
    specific = {variable: result.specific_iia for variable, result in component_results.items()}
    component_delete_one = {
        variable: result.delete_one_by_id for variable, result in component_results.items()
    }
    reference_result = component_results[CAUSAL_VARIABLES[0]]
    reference_omission_ids = set(reference_result.delete_one_by_id)
    for variable in CAUSAL_VARIABLES[1:]:
        result = component_results[variable]
        if result.trial_count != reference_result.trial_count:
            raise CausalProfileError("profile components must share the same full trial_count")
        if set(result.delete_one_by_id) != reference_omission_ids:
            raise CausalProfileError(
                "profile component delete_one_records must share the same "
                "omitted_content_seed_id set"
            )
        if result.delete_one_trial_by_id != reference_result.delete_one_trial_by_id:
            raise CausalProfileError(
                "profile component delete_one_records must share the same trial_count "
                "for every omitted_content_seed_id"
            )

    delta = _mapping(record["delta_specific"], context="delta_specific")
    _exact_keys(
        delta,
        {"value", "delete_one_records", "ci95_lower", "ci95_upper"},
        context="delta_specific",
    )
    delta_value = _number(delta["value"], context="delta_specific.value", minimum=-2, maximum=2)
    expected_delta = specific["semantic_solution"] - specific["surface_cue"]
    if not _close(delta_value, expected_delta, tolerance=ARITHMETIC_TOLERANCE):
        raise CausalProfileError(
            "delta_specific.value must equal semantic specific_iia - surface-cue specific_iia"
        )
    delta_delete_one_raw = delta["delete_one_records"]
    if (
        not isinstance(delta_delete_one_raw, list)
        or len(delta_delete_one_raw) != JACKKNIFE_DELETE_ONE_COUNT
    ):
        raise CausalProfileError(
            "delta_specific.delete_one_records must contain exactly 16 records"
        )
    delta_delete_one_by_id: dict[str, float] = {}
    for index, raw_delete_one in enumerate(delta_delete_one_raw):
        delete_context = f"delta_specific.delete_one_records[{index}]"
        delete_record = _mapping(raw_delete_one, context=delete_context)
        _exact_keys(
            delete_record,
            {"omitted_content_seed_id", "value"},
            context=delete_context,
        )
        omitted_id = _nonempty_text(
            delete_record["omitted_content_seed_id"],
            context=f"{delete_context}.omitted_content_seed_id",
        )
        if omitted_id in delta_delete_one_by_id:
            raise CausalProfileError(
                "delta_specific.delete_one_records omitted_content_seed_id values must be unique"
            )
        delta_delete_one_by_id[omitted_id] = _number(
            delete_record["value"],
            context=f"{delete_context}.value",
            minimum=-2,
            maximum=2,
        )
    if set(delta_delete_one_by_id) != reference_omission_ids:
        raise CausalProfileError(
            "delta_specific.delete_one_records must use the profile omission-ID set"
        )
    for omitted_id, observed in delta_delete_one_by_id.items():
        expected = (
            component_delete_one["semantic_solution"][omitted_id]
            - component_delete_one["surface_cue"][omitted_id]
        )
        if not _close(observed, expected, tolerance=ARITHMETIC_TOLERANCE):
            raise CausalProfileError(
                "delta_specific.delete_one_records must equal semantic minus cue for "
                f"omitted_content_seed_id {omitted_id!r}"
            )
    delta_delete_one = tuple(delta_delete_one_by_id.values())
    delta_lower, delta_upper = _validate_interval(
        value=delta_value,
        lower=delta["ci95_lower"],
        upper=delta["ci95_upper"],
        context="delta_specific",
        minimum=-2,
        maximum=2,
        tolerance=ARITHMETIC_TOLERANCE,
    )
    expected_delta_lower, expected_delta_upper = delete_one_jackknife_interval(
        delta_value,
        delta_delete_one,
        lower_bound=-2,
        upper_bound=2,
    )
    if not _close(delta_lower, expected_delta_lower, tolerance=ARITHMETIC_TOLERANCE) or not _close(
        delta_upper, expected_delta_upper, tolerance=ARITHMETIC_TOLERANCE
    ):
        raise CausalProfileError(
            "delta_specific interval must equal the frozen 16-delete-one jackknife interval"
        )
    codebook_result = _validate_codebook_competence(
        record["codebook_competence"], tolerance=ARITHMETIC_TOLERANCE
    )

    uncertainty = _mapping(record["uncertainty_scope"], context="uncertainty_scope")
    _exact_keys(
        uncertainty,
        {
            "interval_scope",
            "interval_method",
            "primary_independent_unit",
            "population_inference",
        },
        context="uncertainty_scope",
    )
    if uncertainty["interval_scope"] != INTERVAL_SCOPE:
        raise CausalProfileError(
            "pilot causal-profile intervals must be within-target measurement precision"
        )
    if uncertainty["interval_method"] != INTERVAL_METHOD:
        raise CausalProfileError("pilot causal-profile interval method is not frozen")
    if uncertainty["primary_independent_unit"] != PRIMARY_INDEPENDENT_UNIT:
        raise CausalProfileError("primary_independent_unit must be dependency_cluster_id")
    if uncertainty["population_inference"] is not False:
        raise CausalProfileError("pilot causal-profile records cannot assert population inference")

    stability_result = _validate_site_selection_stability(record["site_selection_stability"])
    _validate_gate_evaluation(
        record["gate_evaluation"],
        anchor_condition_id=anchor_condition_id,
        component_results=component_results,
        codebook_result=codebook_result,
        stability_selected_counts=stability_result.selected_counts,
    )

    provenance = _mapping(record["provenance"], context="provenance")
    _exact_keys(
        provenance,
        {
            "execution_lock_sha256",
            "site_discovery_report_sha256",
            "causal_label_evidence_sha256",
            "evaluation_pair_set_sha256",
        },
        context="provenance",
    )
    for field, value in provenance.items():
        _sha256(value, context=f"provenance.{field}")

    return dict(record)


def validate_causal_profile_against_artifact_hashes_non_authoritative(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject aggregate-only provenance; retained as an explicit negative control."""

    _mapping(payload, context="causal profile")
    raise CausalProfileError(
        "aggregate-only provenance cannot authorize a causal profile; provide raw evidence"
    )


def _expected_profile_stability_from_report(
    *,
    report: Mapping[str, Any],
    target_id: str,
) -> dict[str, Any]:
    selected_rows = report.get("selected_sites")
    stability_rows = report.get("site_selection_stability")
    if not isinstance(selected_rows, list) or not isinstance(stability_rows, list):
        raise CausalProfileError(
            "validated site-discovery report lacks selected-site stability evidence"
        )
    selected_by_variable = {
        row.get("causal_variable"): row
        for row in selected_rows
        if isinstance(row, Mapping) and row.get("model_unit_id") == target_id
    }
    stability_by_variable = {
        row.get("causal_variable"): row
        for row in stability_rows
        if isinstance(row, Mapping) and row.get("model_unit_id") == target_id
    }
    if set(selected_by_variable) != set(CAUSAL_VARIABLES) or set(stability_by_variable) != set(
        CAUSAL_VARIABLES
    ):
        raise CausalProfileError(
            "site-discovery report must contain one selected and stability row per target factor"
        )

    components: dict[str, Any] = {}
    all_stable = True
    for variable in CAUSAL_VARIABLES:
        selected = selected_by_variable[variable]
        stability = stability_by_variable[variable]
        if selected.get("selected_site_id") != stability.get("full_data_selected_site_id"):
            raise CausalProfileError(
                f"validated site stability disagrees with the full selected site for {variable}"
            )
        leave_one_raw = stability.get("leave_one_records")
        histogram_raw = stability.get("selection_histogram")
        if not isinstance(leave_one_raw, list) or not isinstance(histogram_raw, list):
            raise CausalProfileError("validated site stability evidence is incomplete")
        positive_histogram = [
            {
                "site_id": row.get("canonical_site_id"),
                "count": row.get("selection_count"),
            }
            for row in histogram_raw
            if isinstance(row, Mapping) and row.get("selection_count", 0) > 0
        ]
        components[variable] = {
            "selected_site_id": stability["full_data_selected_site_id"],
            "candidate_site_count": stability["candidate_site_count"],
            "selection_frequency": stability["selection_frequency"],
            "score_gap_to_runner_up": selected["selection_gap"],
            "leave_one_selections": [
                {
                    "omitted_content_seed_id": row["opaque_content_seed_id"],
                    "selected_site_id": row["selected_site_id"],
                }
                for row in leave_one_raw
            ],
            "selection_histogram": positive_histogram,
        }
        all_stable = all_stable and stability.get("stable") is True
    return {
        "method": SITE_STABILITY_METHOD,
        "resample_count": SITE_STABILITY_RESAMPLE_COUNT,
        "stability_threshold": SITE_STABILITY_THRESHOLD,
        "overall_status": "stable" if all_stable else "unstable",
        "components": components,
    }


def _validate_raw_causal_label_evidence(
    *,
    record: Mapping[str, Any],
    evidence: Mapping[str, Any],
    execution_lock: Mapping[str, Any],
    causal_partition: Mapping[str, Any],
    expected_selected_sites: Mapping[str, str],
    canonical_artifact_sha256: Any,
) -> None:
    from latent_trace_tomography.execution import (
        ExecutionContractError,
        derive_intervention_trial_condition_order,
        validate_intervention_execution_record,
    )
    from latent_trace_tomography.oss_design import parse_final

    context = "causal_label_evidence"
    _exact_keys(
        evidence,
        {
            "schema_version",
            "status",
            "execution_lock_sha256",
            "target_id",
            "unpatched_trials",
            "intervention_trials",
        },
        context=context,
    )
    if evidence["schema_version"] != SCHEMA_VERSION or evidence["status"] != "complete":
        raise CausalProfileError("causal_label_evidence must be complete v0.1.0")
    lock_sha256 = canonical_artifact_sha256(execution_lock)
    if evidence["execution_lock_sha256"] != lock_sha256:
        raise CausalProfileError("causal_label_evidence targets another execution lock")
    if evidence["target_id"] != record["target_id"]:
        raise CausalProfileError("causal_label_evidence targets another model unit")
    evidence_sha256 = canonical_artifact_sha256(evidence)
    if record["provenance"]["causal_label_evidence_sha256"] != evidence_sha256:
        raise CausalProfileError(
            "provenance.causal_label_evidence_sha256 does not match raw evidence"
        )

    prompt_inventory_raw = causal_partition.get("intervention_prompt_inventory")
    if not isinstance(prompt_inventory_raw, list) or len(prompt_inventory_raw) != 128:
        raise CausalProfileError("D_causal_label must bind exactly 128 canonical prompts")
    prompt_inventory = [
        _mapping(item, context=f"D_causal_label prompt inventory[{index}]")
        for index, item in enumerate(prompt_inventory_raw)
    ]
    expected_prompt_ids = [item["prompt_id"] for item in prompt_inventory]
    unpatched_raw = evidence["unpatched_trials"]
    if not isinstance(unpatched_raw, list) or len(unpatched_raw) != 128:
        raise CausalProfileError(
            "causal_label_evidence.unpatched_trials must contain exactly 128 records"
        )
    observed_prompt_ids: list[str] = []
    codebook_success_count = 0
    prompt_fields = {
        "prompt_id",
        "case_id",
        "prompt_sha256",
        "prompt_record_sha256",
        "oracle_final",
        "output_text",
        "output_text_sha256",
        "parsed_final",
        "oracle_correct",
        "activation_capture_record_sha256",
    }
    unpatched_by_prompt_id: dict[str, Mapping[str, Any]] = {}
    for index, (raw_trial, expected_prompt) in enumerate(zip(unpatched_raw, prompt_inventory)):
        trial = _mapping(raw_trial, context=f"unpatched_trials[{index}]")
        _exact_keys(trial, prompt_fields, context=f"unpatched_trials[{index}]")
        for field in (
            "prompt_id",
            "case_id",
            "prompt_sha256",
            "prompt_record_sha256",
            "oracle_final",
        ):
            if trial[field] != expected_prompt[field]:
                raise CausalProfileError(
                    f"unpatched trial {field} differs from the lock-bound prompt inventory"
                )
        output_text = trial["output_text"]
        if not isinstance(output_text, str):
            raise CausalProfileError("unpatched trial output_text must be text")
        expected_output_sha256 = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
        if trial["output_text_sha256"] != expected_output_sha256:
            raise CausalProfileError("unpatched output hash does not bind the raw bytes")
        parsed = parse_final(output_text)
        parsed_value = None if parsed is None else parsed.value
        if trial["parsed_final"] != parsed_value:
            raise CausalProfileError("unpatched parsed_final was not derived from output_text")
        observed_prompt_ids.append(trial["prompt_id"])
        expected_symbol = parse_final(expected_prompt["oracle_final"])
        if expected_symbol is None:  # pragma: no cover - execution validator freezes finals.
            raise CausalProfileError("lock-bound prompt oracle_final is not parseable")
        oracle_correct = parsed == expected_symbol
        if trial["oracle_correct"] is not oracle_correct:
            raise CausalProfileError("unpatched oracle_correct was not derived from raw output")
        _sha256(
            trial["activation_capture_record_sha256"],
            context=f"unpatched_trials[{index}].activation_capture_record_sha256",
        )
        codebook_success_count += int(oracle_correct)
        unpatched_by_prompt_id[trial["prompt_id"]] = trial
    if observed_prompt_ids != expected_prompt_ids or len(set(observed_prompt_ids)) != 128:
        raise CausalProfileError(
            "unpatched trial inventory must exactly preserve the canonical prompt order"
        )

    pair_inventory_raw = causal_partition.get("primary_pair_inventory")
    if not isinstance(pair_inventory_raw, list) or len(pair_inventory_raw) != 192:
        raise CausalProfileError("D_causal_label must bind exactly 192 primary pairs")
    pair_inventory = [
        _mapping(item, context=f"D_causal_label primary pair inventory[{index}]")
        for index, item in enumerate(pair_inventory_raw)
    ]
    intervention_raw = evidence["intervention_trials"]
    if not isinstance(intervention_raw, list) or len(intervention_raw) != 192:
        raise CausalProfileError(
            "causal_label_evidence.intervention_trials must contain exactly 192 records"
        )
    material_fields = {
        "causal_variable",
        "pair_id",
        "opaque_content_seed_id",
        "pair_record_sha256",
        "base_prompt_id",
        "base_prompt_sha256",
        "source_prompt_id",
        "source_prompt_sha256",
        "expected_patched_final",
        "base_oracle_final",
    }
    trial_fields = material_fields | {
        "selected_site_id",
        "base_activation_capture_record_sha256",
        "source_activation_capture_record_sha256",
        "trial_order",
    }
    condition_ids = {
        "targeted_interchange",
        "norm_matched_rotation",
        "self_sham",
        "control_site_delta",
    }
    success_counts: dict[str, Counter[str]] = {variable: Counter() for variable in CAUSAL_VARIABLES}
    seed_success_counts: dict[str, dict[str, Counter[str]]] = {
        variable: {} for variable in CAUSAL_VARIABLES
    }
    observed_pair_ids: list[tuple[str, str]] = []
    expected_pair_ids = [(item["causal_variable"], item["pair_id"]) for item in pair_inventory]
    selected_candidates: dict[str, Mapping[str, Any]] = {}
    for raw_panel in execution_lock["candidate_site_inventory"]:
        panel = _mapping(raw_panel, context="execution_lock.candidate_site_inventory")
        if panel.get("model_unit_id") != record["target_id"]:
            continue
        variable = panel.get("causal_variable")
        if variable not in CAUSAL_VARIABLES:
            continue
        matches = [
            _mapping(candidate, context=f"candidate_site_inventory.{variable}.candidate")
            for candidate in panel.get("candidates", [])
            if isinstance(candidate, Mapping)
            and candidate.get("canonical_site_id") == expected_selected_sites[variable]
        ]
        if len(matches) != 1:
            raise CausalProfileError(
                f"validated execution lock does not retain one selected candidate for {variable}"
            )
        selected_candidates[variable] = matches[0]
    if set(selected_candidates) != set(CAUSAL_VARIABLES):
        raise CausalProfileError(
            "validated execution lock lacks the target's complete selected-candidate inventory"
        )
    carrier_bindings = {
        (
            binding.get("model_unit_id"),
            binding.get("prompt_id"),
            binding.get("causal_variable"),
        ): binding
        for binding in execution_lock["post_discovery_carrier_binding_records"]
        if isinstance(binding, Mapping)
    }
    for index, (raw_trial, expected_pair) in enumerate(zip(intervention_raw, pair_inventory)):
        trial = _mapping(raw_trial, context=f"intervention_trials[{index}]")
        _exact_keys(trial, trial_fields, context=f"intervention_trials[{index}]")
        for field in material_fields:
            if trial[field] != expected_pair[field]:
                raise CausalProfileError(
                    f"intervention trial {field} differs from the lock-bound pair inventory"
                )
        variable = trial["causal_variable"]
        if variable not in CAUSAL_VARIABLES:
            raise CausalProfileError("intervention trial has an unknown causal variable")
        if trial["selected_site_id"] != expected_selected_sites[variable]:
            raise CausalProfileError(
                f"intervention trial for {variable} uses a site not bound by discovery"
            )
        capture_bindings = {
            "base_activation_capture_record_sha256": unpatched_by_prompt_id[
                trial["base_prompt_id"]
            ]["activation_capture_record_sha256"],
            "source_activation_capture_record_sha256": unpatched_by_prompt_id[
                trial["source_prompt_id"]
            ]["activation_capture_record_sha256"],
        }
        for field, expected_capture in capture_bindings.items():
            if trial[field] != expected_capture:
                raise CausalProfileError(
                    f"intervention trial {field} drifted from raw unpatched capture evidence"
                )
        observed_pair_ids.append((variable, trial["pair_id"]))
        expected_patched_symbol = parse_final(trial["expected_patched_final"])
        base_symbol = parse_final(trial["base_oracle_final"])
        if expected_patched_symbol is None or base_symbol is None:
            raise CausalProfileError("lock-bound intervention oracle final is not parseable")
        conditions_raw = trial["trial_order"]
        if not isinstance(conditions_raw, list) or len(conditions_raw) != 4:
            raise CausalProfileError("every intervention pair must retain four raw conditions")
        expected_condition_order = derive_intervention_trial_condition_order(
            partition_id="D_causal_label",
            split_manifest_sha256=execution_lock["split_manifest_sha256"],
            model_unit_id=record["target_id"],
            causal_variable=variable,
            canonical_site_id=trial["selected_site_id"],
            pair_id=trial["pair_id"],
        )
        observed_conditions: set[str] = set()
        seed_id = trial["opaque_content_seed_id"]
        seed_bucket = seed_success_counts[variable].setdefault(seed_id, Counter())
        for condition_index, raw_condition in enumerate(conditions_raw):
            condition = _mapping(
                raw_condition,
                context=f"intervention_trials[{index}].trial_order[{condition_index}]",
            )
            _exact_keys(
                condition,
                {
                    "condition_id",
                    "order_index",
                    "output_text",
                    "output_text_sha256",
                    "parsed_final",
                    "success",
                    "intervention_execution_record",
                    "intervention_execution_record_sha256",
                },
                context=f"intervention_trials[{index}].trial_order[{condition_index}]",
            )
            condition_id = condition["condition_id"]
            if condition_id not in condition_ids or condition_id in observed_conditions:
                raise CausalProfileError(
                    "intervention trial condition ids must be the four frozen unique ids"
                )
            if condition["order_index"] != condition_index:
                raise CausalProfileError("intervention trial order indices must be contiguous")
            if condition_id != expected_condition_order[condition_index]:
                raise CausalProfileError(
                    "intervention condition order differs from the frozen D_causal permutation"
                )
            output_text = condition["output_text"]
            if not isinstance(output_text, str):
                raise CausalProfileError("intervention condition output_text must be text")
            expected_output_sha256 = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
            if condition["output_text_sha256"] != expected_output_sha256:
                raise CausalProfileError("intervention output hash does not bind the raw bytes")
            parsed = parse_final(output_text)
            parsed_value = None if parsed is None else parsed.value
            if condition["parsed_final"] != parsed_value:
                raise CausalProfileError(
                    "intervention parsed_final was not derived from output_text"
                )
            observed_conditions.add(condition_id)
            expected_symbol = (
                base_symbol if condition_id == "self_sham" else expected_patched_symbol
            )
            success_bool = parsed == expected_symbol
            if condition["success"] is not success_bool:
                raise CausalProfileError("intervention success was not derived from raw output")
            try:
                validate_intervention_execution_record(
                    condition["intervention_execution_record"],
                    record_sha256=condition["intervention_execution_record_sha256"],
                    authorization=execution_lock,
                    partition_id="D_causal_label",
                    condition_id=condition_id,
                    order_index=condition_index,
                    model_unit_id=record["target_id"],
                    causal_variable=variable,
                    candidate=selected_candidates[variable],
                    pair=expected_pair,
                    base_capture_sha256=trial["base_activation_capture_record_sha256"],
                    source_capture_sha256=trial["source_activation_capture_record_sha256"],
                    base_binding=carrier_bindings[
                        (record["target_id"], trial["base_prompt_id"], variable)
                    ],
                    source_binding=carrier_bindings[
                        (record["target_id"], trial["source_prompt_id"], variable)
                    ],
                    output_text_sha256=condition["output_text_sha256"],
                    context=(
                        f"intervention_trials[{index}].trial_order"
                        f"[{condition_index}].intervention_execution_record"
                    ),
                )
            except (ExecutionContractError, KeyError) as exc:
                raise CausalProfileError(
                    f"intervention execution provenance failed structural validation: {exc}"
                ) from exc
            success = int(success_bool)
            success_counts[variable][condition_id] += success
            seed_bucket[condition_id] += success
        if observed_conditions != condition_ids:
            raise CausalProfileError("intervention trial is missing a frozen condition")
    if observed_pair_ids != expected_pair_ids or len(set(observed_pair_ids)) != 192:
        raise CausalProfileError(
            "intervention trials must exactly preserve the D_causal_label primary-pair order"
        )

    condition_to_profile_field = {
        "targeted_interchange": "intended_success_count",
        "norm_matched_rotation": "matched_null_success_count",
    }
    for variable in CAUSAL_VARIABLES:
        component = record["profile"][variable]
        if len(seed_success_counts[variable]) != 16:
            raise CausalProfileError(
                f"raw {variable} evidence must contain exactly 16 content-seed blocks"
            )
        pair_seed_counts = Counter(
            item["opaque_content_seed_id"]
            for item in pair_inventory
            if item["causal_variable"] == variable
        )
        if set(pair_seed_counts.values()) != {4} or set(pair_seed_counts) != set(
            seed_success_counts[variable]
        ):
            raise CausalProfileError(
                f"raw {variable} evidence must contain four pairs for each causal-label seed"
            )
        for condition_id, profile_field in condition_to_profile_field.items():
            if component[profile_field] != success_counts[variable][condition_id]:
                raise CausalProfileError(
                    f"profile.{variable}.{profile_field} differs from raw parsed outcomes"
                )
        controls = component["specificity_controls"]
        if controls["self_sham"]["success_count"] != success_counts[variable]["self_sham"]:
            raise CausalProfileError(
                f"profile.{variable} self-sham count differs from raw parsed outcomes"
            )
        if (
            controls["control_site_delta"]["success_count"]
            != success_counts[variable]["control_site_delta"]
        ):
            raise CausalProfileError(
                f"profile.{variable} control-site count differs from raw parsed outcomes"
            )
        delete_one_by_seed = {
            item["omitted_content_seed_id"]: item for item in component["delete_one_records"]
        }
        if set(delete_one_by_seed) != set(seed_success_counts[variable]):
            raise CausalProfileError(
                f"profile.{variable} delete-one ids differ from raw causal-label seeds"
            )
        for seed_id, seed_counts in seed_success_counts[variable].items():
            delete_record = delete_one_by_seed[seed_id]
            expected_intended = (
                success_counts[variable]["targeted_interchange"]
                - seed_counts["targeted_interchange"]
            )
            expected_matched = (
                success_counts[variable]["norm_matched_rotation"]
                - seed_counts["norm_matched_rotation"]
            )
            if (
                delete_record["trial_count"] != 60
                or delete_record["intended_success_count"] != expected_intended
                or delete_record["matched_null_success_count"] != expected_matched
            ):
                raise CausalProfileError(
                    f"profile.{variable} delete-one counts differ from raw evidence"
                )

    competence = record["codebook_competence"]
    if (
        competence["trial_count"] != 128
        or competence["success_count"] != codebook_success_count
        or competence["causal_label_case_set_sha256"] != causal_partition["case_set_sha256"]
    ):
        raise CausalProfileError(
            "codebook_competence differs from the 128 raw D_causal_label outputs"
        )


def validate_causal_profile(
    payload: Mapping[str, Any],
    *,
    discovery_authorization: Mapping[str, Any],
    execution_lock: Mapping[str, Any],
    site_discovery_report: Mapping[str, Any],
    causal_label_evidence: Mapping[str, Any],
    authority_secret: bytes,
    expected_parent_design_manifest_sha256: str,
    expected_parent_discovery_template_sha256: str,
    expected_parent_execution_template_sha256: str,
    expected_prospective_contract: Mapping[str, str],
) -> dict[str, Any]:
    """Authorize one causal profile from frozen ancestry and raw output evidence."""

    from latent_trace_tomography.execution import (
        ExecutionContractError,
        canonical_artifact_sha256,
        validate_discovery_readiness,
        validate_execution_lock,
        validate_site_discovery_report,
    )

    trusted_roots = {
        "expected_parent_design_manifest_sha256": expected_parent_design_manifest_sha256,
        "expected_parent_discovery_template_sha256": (expected_parent_discovery_template_sha256),
        "expected_parent_execution_template_sha256": (expected_parent_execution_template_sha256),
    }
    try:
        validate_discovery_readiness(
            discovery_authorization,
            authority_secret=authority_secret,
            **trusted_roots,
        )
        validate_site_discovery_report(
            site_discovery_report,
            authorization=discovery_authorization,
            **trusted_roots,
        )
        validate_execution_lock(
            execution_lock,
            authorization=discovery_authorization,
            site_discovery_report=site_discovery_report,
            expected_prospective_contract=expected_prospective_contract,
            **trusted_roots,
        )
    except ExecutionContractError as exc:
        raise CausalProfileError(
            f"trusted execution ancestry failed structural validation: {exc}"
        ) from exc

    record = validate_causal_profile_record_non_authoritative(payload)
    lock_sha256 = canonical_artifact_sha256(execution_lock)
    report_sha256 = canonical_artifact_sha256(site_discovery_report)
    if record["provenance"]["execution_lock_sha256"] != lock_sha256:
        raise CausalProfileError(
            "provenance.execution_lock_sha256 does not match the validated execution lock"
        )
    if record["provenance"]["site_discovery_report_sha256"] != report_sha256:
        raise CausalProfileError(
            "provenance.site_discovery_report_sha256 does not match the validated report"
        )

    registry = execution_lock["model_registry"]
    matching_models = [row for row in registry if row.get("model_unit_id") == record["target_id"]]
    if len(matching_models) != 1:
        raise CausalProfileError(
            "causal profile target_id must match exactly one validated model_registry row"
        )
    model_row = matching_models[0]
    identity_mapping = {
        "family_id": "architecture_family_id",
        "dependency_cluster_id": "dependency_cluster_id",
        "training_lineage_id": "lineage_id",
        "checkpoint_id": "checkpoint_id",
        "anchor_condition_id": "anchor_condition_id",
    }
    for profile_field, registry_field in identity_mapping.items():
        if record[profile_field] != model_row[registry_field]:
            raise CausalProfileError(
                f"causal profile {profile_field} disagrees with model_registry.{registry_field}"
            )

    expected_stability = _expected_profile_stability_from_report(
        report=site_discovery_report,
        target_id=record["target_id"],
    )
    if record["site_selection_stability"] != expected_stability:
        raise CausalProfileError(
            "profile site_selection_stability differs from raw report-derived rediscovery"
        )
    selected_site_ids = {
        variable: expected_stability["components"][variable]["selected_site_id"]
        for variable in CAUSAL_VARIABLES
    }

    partitions = [
        item
        for item in execution_lock["live_material_manifest"]["partition_records"]
        if item.get("partition_id") == "D_causal_label"
    ]
    if len(partitions) != 1:
        raise CausalProfileError("validated execution lock lacks one D_causal_label partition")
    causal_partition = partitions[0]
    if (
        causal_partition["content_seed_count"] != 16
        or causal_partition["case_count"] != 128
        or causal_partition["primary_intervention_pair_count"] != 192
        or causal_partition["primary_pair_count_by_causal_variable"]
        != {variable: 64 for variable in CAUSAL_VARIABLES}
    ):
        raise CausalProfileError("validated D_causal_label partition denominators drifted")
    causal_pair_hash = causal_partition["primary_intervention_pair_set_sha256"]
    if execution_lock["causal_label_primary_intervention_pair_set_sha256"] != causal_pair_hash:
        raise CausalProfileError("execution lock causal-label pair binding drifted")
    if record["provenance"]["evaluation_pair_set_sha256"] != causal_pair_hash:
        raise CausalProfileError(
            "profile evaluation_pair_set_sha256 must bind the D_causal_label subset"
        )

    _validate_raw_causal_label_evidence(
        record=record,
        evidence=_mapping(causal_label_evidence, context="causal_label_evidence"),
        execution_lock=execution_lock,
        causal_partition=causal_partition,
        expected_selected_sites=selected_site_ids,
        canonical_artifact_sha256=canonical_artifact_sha256,
    )
    return record
