"""Numerical acceptance rules for offline reproducibility comparisons."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

SERIALIZATION_ABSOLUTE_TOLERANCE = 1e-15
COSINE_ABSOLUTE_TOLERANCE = 1e-15


def numeric_comparison(
    left: np.ndarray,
    right: np.ndarray,
    *,
    atol: float = 0.0,
    allow_matching_nan: bool = False,
) -> dict[str, Any]:
    """Keep exact equality separate from explicitly bounded equivalence.

    Infinity is never accepted. Matching NaNs may represent intentionally
    missing aligned alternate bases, and must be explicitly enabled by callers.
    Empty or differently shaped arrays cannot establish reproduction.
    """
    if not math.isfinite(atol) or atol < 0:
        raise ValueError("The absolute tolerance must be finite and nonnegative")
    left, right = np.asarray(left), np.asarray(right)
    result: dict[str, Any] = {
        "same_shape": left.shape == right.shape,
        "left_shape": list(left.shape),
        "right_shape": list(right.shape),
        "exact": False,
        "max_abs_difference": None,
        "nan_pattern_exact": False,
        "finite_pattern_exact": False,
        "has_infinity": bool(np.isinf(left).any() or np.isinf(right).any()),
        "equivalent_at_serialization_tolerance": False,
        "absolute_tolerance": atol,
        "relative_tolerance": 0.0,
        "matching_nan_allowed": allow_matching_nan,
    }
    if not result["same_shape"]:
        return result
    result["shape"] = list(left.shape)
    result["exact"] = bool(np.array_equal(left, right, equal_nan=True))
    result["nan_pattern_exact"] = bool(np.array_equal(np.isnan(left), np.isnan(right)))
    left_finite, right_finite = np.isfinite(left), np.isfinite(right)
    result["finite_pattern_exact"] = bool(np.array_equal(left_finite, right_finite))
    comparable = left_finite & right_finite
    with np.errstate(over="ignore", invalid="ignore"):
        difference = float(np.max(np.abs(left[comparable] - right[comparable]))) if comparable.any() else 0.0
    result["max_abs_difference"] = difference if math.isfinite(difference) else None
    valid_nan = result["nan_pattern_exact"] and (
        allow_matching_nan or not (np.isnan(left).any() or np.isnan(right).any())
    )
    result["equivalent_at_serialization_tolerance"] = bool(
        left.size > 0 and comparable.any() and valid_nan
        and result["finite_pattern_exact"] and not result["has_infinity"]
        and math.isfinite(difference) and difference <= atol
    )
    return result


def single_reference_passed(contexts: list[dict]) -> bool:
    """All requested per-track and consensus sealed-reference checks must pass."""
    if not contexts:
        return False
    for row in contexts:
        reference = row["fresh_vs_sealed_v0_20"]
        for column in ("raw_score", "null_median", "effect"):
            result = reference["track_values"][column]
            if not (result["exact"] is True and result["changed_tracks"] == 0
                    and result["max_abs_difference"] == 0):
                return False
        for field in ("real_consensus_delta", "empirical_p_two_sided", "empirical_p_observed_direction"):
            result = reference["summary"][field]
            if not (result["exact"] is True and result["difference"] == 0
                    and math.isfinite(result["fresh"]) and math.isfinite(result["v0_20"])):
                return False
    return True


def cohort_reference_passed(reference: dict) -> bool:
    """Matrix and statistics require exact equality; cosine has an absolute bound."""
    exact_checks = [reference["matrix"], *reference["statistics"].values()]
    if len(reference["statistics"]) != 5:
        return False
    if not all(check["exact"] is True and check["max_abs_difference"] == 0 for check in exact_checks):
        return False
    cosine = reference["cosine"]
    return bool(cosine["equivalent_at_absolute_tolerance"] is True
                and math.isfinite(cosine["max_abs_difference"])
                and cosine["max_abs_difference"] <= COSINE_ABSOLUTE_TOLERANCE)


def validate_recorded_reports(single: dict, cohort: dict, curves: dict) -> dict:
    """Re-evaluate recorded comparison facts without trusting top-level status.

    This validates report consistency and acceptance thresholds. It cannot
    authenticate raw files or establish independent provider requests.
    """
    errors = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    def finite_tree(value: Any) -> bool:
        if isinstance(value, float):
            return math.isfinite(value)
        if isinstance(value, dict):
            return all(finite_tree(item) for item in value.values())
        if isinstance(value, list):
            return all(finite_tree(item) for item in value)
        return True

    try:
        for label, report in (("single", single), ("cohort", cohort), ("curves", curves)):
            require(report["status"] == "passed", label + ":recorded_status")
            require(report["provider_calls"] == 0, label + ":offline_provider_calls")
            require(finite_tree(report), label + ":nonfinite_number")
        contexts = single["contexts"]
        ids = [row["context"] for row in contexts]
        require(len(ids) == len(set(ids)) == 19 and {"rbfox1_16kb", "ptchd1_1mb"} <= set(ids), "single:context_count_or_identity")
        require(single_reference_passed(contexts), "single:sealed_reference_mismatch")
        required_summary = {"real_consensus_delta", "empirical_p_two_sided", "empirical_p_observed_direction",
                            "n_null_consensus", "n_real_brain_groups", "n_real_brain_tracks", "primary_effect_scope"}
        for row in contexts:
            parity = row["fresh_web_vs_github"]
            require(parity["status"] == "exact", "single:software_parity")
            require(parity["table_rows"] == {"group_summary": 11, "null_consensus": 1000,
                                             "null_group_medians": 1000, "source_table": 371}, "single:table_depth")
            require(required_summary <= set(parity["summary_fields_exact"]), "single:summary_coverage")
        require(cohort["n_variants"] == 17 and cohort["scope"] == "brain9_adult8_embryo", "cohort:scope_or_count")
        require(cohort["reference_variant_group_id"] == "RBFOX1_del3", "cohort:reference_variant")
        for label, rows in (("matrix", 17), ("ranking", 17), ("cosine", 17), ("nulls", 17000)):
            parity = cohort["fresh_web_vs_github"][label]
            require(parity["exact"] is True and parity["rows"] == rows, "cohort:" + label + "_parity")
        reference = cohort["fresh_vs_sealed_v0_20"]
        for label, check in [("matrix", reference["matrix"]), *reference["statistics"].items()]:
            require(check["exact"] is True and check["max_abs_difference"] == 0
                    and check.get("changed_cells", check.get("changed_variants")) == 0, "cohort:" + label + "_reference")
        require(len(reference["statistics"]) == 5, "cohort:statistics_coverage")
        cosine = reference["cosine"]
        require(0 <= cosine["max_abs_difference"] <= COSINE_ABSOLUTE_TOLERANCE, "cohort:cosine_tolerance")
        require((cosine["exact"] is True) == (cosine["changed_variants"] == 0 and cosine["max_abs_difference"] == 0), "cohort:cosine_exact_consistency")
        require(set(curves["contexts"]) == {"rbfox1_16kb", "ptchd1_1mb"}, "curves:context_identity")
        for name, result in curves["contexts"].items():
            require(result["selection_exact"] is True and result["all_numeric_equivalent"] is True, "curves:" + name + "_summary")
            selection = result["selection"]
            for flag, field in (("interval_exact", "interval"), ("ontology_exact", "ontology_terms"),
                                ("track_identity_exact", "track_identity")):
                require(selection[flag] is True and selection["sealed"][field] == selection["fresh"][field], "curves:" + name + "_" + flag)
            identity = selection["fresh"]["track_identity"]
            require(identity["ontology_curie"] == "UBERON:0001870" and identity["gtex_tissue"] == "Brain_Cortex"
                    and identity["biosample_life_stage"] == "adult" and identity["strand"] == ".", "curves:" + name + "_frontal_cortex")
            for kind in ("raw", "aligned"):
                for column in ("position", "ref_prediction", "alt_prediction"):
                    check = result[kind][column]
                    tolerance = SERIALIZATION_ABSOLUTE_TOLERANCE if name == "ptchd1_1mb" and column != "position" else 0.0
                    require(check["same_shape"] is True and check["shape"] == [16384 if name == "rbfox1_16kb" else 1048576], "curves:" + name + "_shape")
                    require(check["nan_pattern_exact"] is True and check["equivalent_at_serialization_tolerance"] is True
                            and 0 <= check["max_abs_difference"] <= tolerance, "curves:" + name + "_numeric_tolerance")
                    if tolerance == 0:
                        require(check["exact"] is True, "curves:" + name + "_exact_required")
                    if "has_infinity" in check:
                        require(check["has_infinity"] is False and check["finite_pattern_exact"] is True, "curves:" + name + "_nonfinite")
    except (KeyError, TypeError, ValueError):
        errors.append("unsupported_or_incomplete_report_schema")
    return {
        "status": "failed" if errors else "passed", "errors": sorted(set(errors)),
        "provider_calls": 0, "offline": True,
        "single_contexts_required": 19, "cohort_variants_required": 17,
        "cosine_absolute_tolerance": COSINE_ABSOLUTE_TOLERANCE,
        "curve_serialization_absolute_tolerance": SERIALIZATION_ABSOLUTE_TOLERANCE,
        "interpretation": "Acceptance and internal consistency of supplied recorded comparisons only; raw artifacts and provider independence are not revalidated by this report-only check.",
    }
