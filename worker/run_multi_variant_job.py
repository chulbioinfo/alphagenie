from __future__ import annotations
from html import escape

import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42})
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
import numpy as np
import pandas as pd

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.job_store import create_job, get_job, update_job
from worker.inference_provenance import figure_provenance_label
from worker.run_single_variant_job import (
    FULL_GROUP_ORDER,
    PLOT_SECTION_BOUNDARIES,
    PLOT_SECTION_LABELS,
    run_job,
    write_json,
    write_text,
)


BLUE = "#2166AC"
RED = "#B2182B"
DARK = "#222222"
GRAY = "#777777"

from worker.brain9 import (
    BRAIN_TISSUE_GROUPS, DISPLAY_ONLY_GROUPS, SCOPE as BRAIN9_SCOPE,
    VERSION as CLASSIFICATION_VERSION, provenance as classification_provenance,
)
BRAIN_GROUPS = list(BRAIN_TISSUE_GROUPS)


def safe_id(value: object, fallback: str = "variant") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or fallback)).strip("_")
    return cleaned or fallback


def bh_adjust(values: list[float | None]) -> list[float | None]:
    indexed = [(idx, float(value)) for idx, value in enumerate(values) if value is not None and np.isfinite(value)]
    if not indexed:
        return [None for _ in values]
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    adjusted = [None for _ in values]
    running = 1.0
    for rank_from_end, (idx, pvalue) in enumerate(reversed(indexed), start=1):
        rank = m - rank_from_end + 1
        running = min(running, pvalue * m / rank)
        adjusted[idx] = float(min(1.0, running))
    return adjusted


def read_json(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def finite_float(value: object) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def cosine(a: list[float | None], b: list[float | None]) -> tuple[float | None, float | None, int]:
    if len(a) != 9 or len(b) != 9 or any(finite_float(x) is None for x in [*a, *b]):
        raise ValueError("Brain9 cosine requires all nine finite category values")
    pairs = list(zip(a, b, strict=True))
    av, bv = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    sim = float(np.clip(np.dot(av, bv) / denom, -1, 1)) if denom > 0 else None
    nz = [(x, y) for x, y in pairs if x != 0 and y != 0]
    agreement = float(sum(math.copysign(1, x) == math.copysign(1, y) for x, y in nz) / len(nz)) if nz else None
    return sim, agreement, len(pairs)


def load_single_result(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result") or {}
    if not isinstance(result, dict):
        result = {}
    summary_path = Path(str(result.get("consensus_summary", "")))
    group_path = Path(str(result.get("group_summary", "")))
    source_path = Path(str(result.get("source_table", "")))
    if not summary_path.exists() or not group_path.exists() or not source_path.exists():
        raise FileNotFoundError(f"single-variant result artifacts are incomplete for {job.get('job_id')}")
    return {
        "job": job,
        "summary": read_json(summary_path),
        "group": pd.read_csv(group_path, sep="\t", float_precision="round_trip"),
        "source": pd.read_csv(source_path, sep="\t", float_precision="round_trip"),
    }


def combine_single_results(
    *,
    job_id: str,
    payload: dict[str, Any],
    single_results: list[dict[str, Any]],
    results_dir: Path,
) -> dict[str, Any]:
    results_dir.mkdir(parents=True, exist_ok=True)
    requested = payload.get("rows") or []
    if not requested or len(single_results) != len(requested):
        raise ValueError("Cohort requires every requested variant; no reduced-family summary")
    expected_ids = [str(row["variant_group_id"]) for row in requested]
    actual_ids = [str(item["summary"].get("variant_group_id")) for item in single_results]
    if len(set(expected_ids)) != len(expected_ids) or set(actual_ids) != set(expected_ids):
        raise ValueError("Cohort variant identities differ from the requested family")
    group_names = [group for group, _ in FULL_GROUP_ORDER]
    rows_for_matrix: list[dict[str, Any]] = []
    ranking_rows: list[dict[str, Any]] = []
    source_tables = []
    p_obs: list[float | None] = []
    p_two: list[float | None] = []

    expected_tracks = None
    for item in single_results:
        summary = item["summary"]
        if summary.get("classification", {}).get("version") != CLASSIFICATION_VERSION or summary.get("primary_effect_scope") != BRAIN9_SCOPE:
            raise ValueError("Cohort requires the same versioned Brain9 classification for every variant")
        group = item["group"]
        source = item["source"].copy()
        sub_job = item["job"]
        tracks = set(source["track_key"]) if "track_key" in source else set()
        if not tracks or (expected_tracks is not None and tracks != expected_tracks):
            raise ValueError("Cohort track membership differs between variants")
        expected_tracks = tracks
        variant_group_id = str(summary.get("variant_group_id") or sub_job.get("input", {}).get("variant_group_id"))
        gene_symbol = str(summary.get("gene_symbol") or sub_job.get("input", {}).get("gene_symbol"))
        source["multi_job_id"] = job_id
        source["single_job_id"] = sub_job.get("job_id")
        source_tables.append(source)

        group_by_name = group.set_index("display_group")["median_effect"].to_dict()
        matrix_row = {
            "variant_group_id": variant_group_id,
            "gene_symbol": gene_symbol,
        }
        for group_name in group_names:
            matrix_row[group_name] = group_by_name.get(group_name)
        rows_for_matrix.append(matrix_row)

        obs = finite_float(summary.get("empirical_p_observed_direction"))
        two = finite_float(summary.get("empirical_p_two_sided"))
        if obs is None or two is None:
            raise ValueError("Cohort empirical P must be finite for every requested variant")
        p_obs.append(obs)
        p_two.append(two)
        ranking_rows.append(
            {
                "variant_group_id": variant_group_id,
                "gene_symbol": gene_symbol,
                "target_gene": summary.get("target_gene"),
                "variant_class": summary.get("variant_class"),
                "chrom": summary.get("chrom"),
                "pos1": summary.get("pos1"),
                "ref": summary.get("ref"),
                "alt": summary.get("alt"),
                "sequence_length": summary.get("sequence_length"),
                "n_null_consensus": summary.get("n_null_consensus"),
                "real_consensus_delta": summary.get("real_consensus_delta"),
                "direction_observed": summary.get("direction_observed"),
                "empirical_p_observed_direction": obs,
                "empirical_p_two_sided": two,
                "single_job_id": sub_job.get("job_id"),
                "single_run_mode": sub_job.get("run_mode"),
            }
        )

    obs_fdr = bh_adjust(p_obs)
    two_fdr = bh_adjust(p_two)
    for row, obs_adj, two_adj in zip(ranking_rows, obs_fdr, two_fdr, strict=False):
        row["bh_fdr_observed_direction_multi"] = obs_adj
        row["bh_fdr_two_sided_multi"] = two_adj

    matrix = pd.DataFrame(rows_for_matrix)
    ranking = pd.DataFrame(ranking_rows)
    group_track_counts = single_results[0]["source"].groupby("display_group")["track_key"].nunique().to_dict()
    reference_id = str(payload.get("reference_variant_group_id") or "")
    if not reference_id and not ranking.empty:
        reference_id = str(ranking.iloc[0]["variant_group_id"])
    reference_row = matrix[matrix["variant_group_id"].astype(str).eq(reference_id)]
    if reference_row.empty:
        raise ValueError("Requested cosine reference is unavailable; no automatic reference substitution")
    ref_values = [finite_float(reference_row.iloc[0].get(group)) for group in BRAIN_GROUPS] if not reference_row.empty else []
    cosine_rows = []
    for _, row in matrix.iterrows():
        values = [finite_float(row.get(group)) for group in BRAIN_GROUPS]
        sim, agreement, n_groups = cosine(values, ref_values)
        cosine_rows.append(
            {
                "variant_group_id": row["variant_group_id"],
                "gene_symbol": row["gene_symbol"],
                "reference_variant_group_id": reference_id,
                "brain_cosine_similarity": sim,
                "brain_sign_agreement": agreement,
                "n_brain_groups_used": n_groups,
            }
        )
    cosine_table = pd.DataFrame(cosine_rows)
    combined_source = pd.concat(source_tables, ignore_index=True) if source_tables else pd.DataFrame()

    combined_source.to_csv(results_dir / "source_table.tsv", sep="\t", index=False)
    null_tables = []
    for item in single_results:
        null_path = Path(item['job']['job_dir']) / 'results/null_consensus.tsv'
        if null_path.is_file():
            table = pd.read_csv(null_path, sep='\t', float_precision='round_trip')
            table.insert(0, 'variant_group_id', item['summary']['variant_group_id'])
            null_tables.append(table)
    if len(null_tables) == len(single_results) and null_tables:
        pd.concat(null_tables, ignore_index=True).to_csv(results_dir / 'multi_null_consensus.tsv', sep='\t', index=False)
    matrix.to_csv(results_dir / "multi_group_matrix.tsv", sep="\t", index=False)
    ranking.to_csv(results_dir / "multi_consensus_ranking.tsv", sep="\t", index=False)
    cosine_table.to_csv(results_dir / "multi_reference_cosine.tsv", sep="\t", index=False)

    summary = {
        "multi_job_id": job_id,
        "analysis_mode": payload.get("analysis_mode"),
        "dataset_name": payload.get("dataset_name"),
        "reference_variant_group_id": reference_id,
        "n_variants_requested": len(payload.get("rows") or []),
        "n_variants_completed": len(single_results),
        "effect_definition": "GeneMaskLFC score minus trackwise matched-null median (predicted RNA log fold change, ALT versus REF)",
        "primary_inference": "two-sided empirical p and BH FDR; observed-direction one-sided values are exploratory",
        "similarity_scope": BRAIN9_SCOPE,
        "classification": classification_provenance(),
        "primary_effect_scope": BRAIN9_SCOPE,
        "primary_effect_groups": BRAIN_GROUPS,
        "display_only_groups": list(DISPLAY_ONLY_GROUPS),
        "heatmap_groups": BRAIN_GROUPS,
        "matrix_groups": group_names,
        "group_track_counts": {key: int(value) for key, value in group_track_counts.items()},
        "heatmap_row_order": payload.get("heatmap_row_order") or "consensus",
        "source_tables": {
            "source_table": "source_table.tsv",
            "matrix": "multi_group_matrix.tsv",
            "ranking": "multi_consensus_ranking.tsv",
            "cosine": "multi_reference_cosine.tsv",
        },
    }
    real_provenance = (single_results[0]['summary'].get('scoring_provenance') or {}).get('real') if single_results else None
    if real_provenance:
        fields = ('inference_backend_revision', 'inference_run_epoch', 'alphagenome_client_version',
                  'requested_model_version', 'genome_build', 'gencode_gtf_identity', 'provenance_schema_version')
        summary['inference_provenance'] = {key: real_provenance.get(key) for key in fields}
        ends = [str(provenance.get('inference_completed_at') or '') for item in single_results
                for provenance in (item['summary'].get('scoring_provenance') or {}).values()]
        summary['inference_completed_at'] = max(ends, default='')
    write_json(results_dir / "multi_consensus_summary.json", summary)
    write_multi_qc_summary(results_dir / "qc_summary.md", payload, summary, ranking, cosine_table)
    make_multi_plot(
        matrix=matrix,
        ranking=ranking,
        cosine_table=cosine_table,
        reference_id=reference_id,
        heatmap_row_order=str(payload.get("heatmap_row_order") or "consensus"),
        out_prefix=results_dir / "multi_variant_plot",
        provenance_label=figure_provenance_label(summary),
        group_track_counts=group_track_counts,
    )
    write_multi_plot_html(results_dir / "multi_variant_plot.html", results_dir / "multi_variant_plot.svg", summary)
    return summary


def write_multi_qc_summary(
    path: Path,
    payload: dict[str, Any],
    summary: dict[str, Any],
    ranking: pd.DataFrame,
    cosine_table: pd.DataFrame,
) -> None:
    validation = payload.get("validation") or {}
    lines = [
        "# Multi-Variant QC Summary",
        "",
        f"- analysis_mode: `{payload.get('analysis_mode')}`",
        f"- dataset_name: `{payload.get('dataset_name')}`",
        f"- reference_variant_group_id: `{summary.get('reference_variant_group_id')}`",
        f"- variants_requested: `{summary.get('n_variants_requested')}`",
        f"- variants_completed: `{summary.get('n_variants_completed')}`",
        f"- similarity_scope: `{summary.get('similarity_scope')}`",
        f"- heatmap_row_order: `{summary.get('heatmap_row_order')}`",
        f"- validation_status: `{validation.get('overall_status', 'not recorded')}`",
        "",
        "## Completed Variants",
    ]
    for _, row in ranking.iterrows():
        lines.append(
            "- `{variant_group_id}` `{gene_symbol}` adjusted RNA log fold change=`{delta}` exploratory observed-direction FDR=`{fdr_obs}` two-sided FDR=`{fdr_two}`".format(
                variant_group_id=row.get("variant_group_id"),
                gene_symbol=row.get("gene_symbol"),
                delta=row.get("real_consensus_delta"),
                fdr_obs=row.get("bh_fdr_observed_direction_multi"),
                fdr_two=row.get("bh_fdr_two_sided_multi"),
            )
        )
    lines.extend(["", "## Reference Similarity"])
    for _, row in cosine_table.iterrows():
        lines.append(
            f"- `{row.get('variant_group_id')}` cosine=`{row.get('brain_cosine_similarity')}` "
            f"sign_agreement=`{row.get('brain_sign_agreement')}`"
        )
    lines.extend(
        [
            "",
            "## Integrity Notes",
            "- Multi-variant statistics are computed from completed single-variant source artifacts.",
            "- Failed sub-jobs are not converted into PASS calls.",
            "- Exploratory runs must not be described as publication-ready when null depth is below 1000.",
        ]
    )
    write_text(path, "\n".join(lines) + "\n")


DEFAULT_MULTI_FIGURE_WIDTH_MM = 170.0
DEFAULT_MULTI_FIGURE_HEIGHT_MM = 92.0
DEFAULT_MULTI_FONT_SIZE_PT = 5.0


def _multi_font(value: float, scale: float) -> float:
    return max(1.0, value * scale)


def _panel_weight(value: float | None, default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.25, min(6.0, parsed))


def make_multi_plot(
    *,
    matrix: pd.DataFrame,
    ranking: pd.DataFrame,
    cosine_table: pd.DataFrame,
    reference_id: str,
    heatmap_row_order: str,
    out_prefix: Path,
    figure_width_mm: float | None = None,
    figure_height_mm: float | None = None,
    font_size_pt: float | None = None,
    heatmap_panel_width: float | None = None,
    fdr_panel_width: float | None = None,
    cosine_panel_width: float | None = None,
    provenance_label: str | None = None,
    group_track_counts: dict[str, int] | None = None,
) -> None:
    width_mm = float(figure_width_mm or DEFAULT_MULTI_FIGURE_WIDTH_MM)
    height_mm = float(figure_height_mm or DEFAULT_MULTI_FIGURE_HEIGHT_MM)
    scale = max(0.15, min(2.8, float(font_size_pt or DEFAULT_MULTI_FONT_SIZE_PT) / DEFAULT_MULTI_FONT_SIZE_PT))
    width_ratios = [
        _panel_weight(heatmap_panel_width, 2.0),
        _panel_weight(fdr_panel_width, 2.0),
        _panel_weight(cosine_panel_width, 1.0),
    ]
    group_names = BRAIN_GROUPS
    labels = [label for _, label in FULL_GROUP_ORDER[:9]]
    if group_track_counts is not None:
        labels = [f"{label} ({group_track_counts[group]})" for group, label in FULL_GROUP_ORDER[:9]]
    ranking = ranking.copy()
    ranking["real_consensus_delta_num"] = pd.to_numeric(ranking["real_consensus_delta"], errors="coerce")
    if heatmap_row_order == "cosine" and not cosine_table.empty:
        cosine_order = (
            cosine_table.assign(
                brain_cosine_similarity_num=pd.to_numeric(
                    cosine_table["brain_cosine_similarity"], errors="coerce"
                )
            )
            .sort_values("brain_cosine_similarity_num", ascending=False)
            ["variant_group_id"]
            .astype(str)
            .tolist()
        )
        ranking = ranking.set_index("variant_group_id").reindex(cosine_order).reset_index()
    else:
        ranking = ranking.sort_values("real_consensus_delta_num", ascending=True)
    ranking = ranking.reset_index(drop=True)
    order = ranking["variant_group_id"].astype(str).tolist()
    gene_counts = ranking["gene_symbol"].astype(str).value_counts().to_dict()

    def variant_axis_label(row: pd.Series) -> str:
        gene = str(row.get("gene_symbol") or "")
        variant_id = str(row.get("variant_group_id") or gene)
        if gene_counts.get(gene, 0) <= 1:
            return gene
        pos1 = row.get("pos1")
        if pos1 is not None and not pd.isna(pos1):
            try:
                pos_label = str(int(float(pos1)))
            except (TypeError, ValueError):
                pos_label = str(pos1)
            return f"{gene}:{pos_label[-5:]}"
        suffix = variant_id
        prefix = f"{gene}_"
        if suffix.startswith(prefix):
            suffix = suffix[len(prefix) :]
        return f"{gene}:{suffix}"

    label_by_variant = {
        str(row.get("variant_group_id")): variant_axis_label(row)
        for _, row in ranking.iterrows()
    }
    ref_gene = str(
        ranking.loc[ranking["variant_group_id"].astype(str).eq(str(reference_id)), "gene_symbol"].iloc[0]
        if not ranking.loc[ranking["variant_group_id"].astype(str).eq(str(reference_id)), "gene_symbol"].empty
        else "Reference"
    )
    matrix = matrix.set_index("variant_group_id").reindex(order).reset_index()
    gene_labels = [
        label_by_variant.get(str(row.get("variant_group_id")), str(row.get("gene_symbol") or ""))
        for _, row in matrix.iterrows()
    ]
    values = matrix[group_names].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    finite_values = values[np.isfinite(values)]
    vmax = max(0.04, float(np.nanmax(np.abs(finite_values))) if finite_values.size else 0.04)
    cmap = LinearSegmentedColormap.from_list("signed_delta", [BLUE, "#F7F7F7", RED])
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)

    fig = plt.figure(figsize=(width_mm / 25.4, height_mm / 25.4), constrained_layout=False)
    gs = fig.add_gridspec(1, 3, width_ratios=width_ratios, wspace=0.34)
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[0, 1])
    ax2 = fig.add_subplot(gs[0, 2])

    im = ax0.imshow(values, aspect="auto", cmap=cmap, norm=norm)
    ax0.set_yticks(np.arange(len(gene_labels)))
    ax0.set_yticklabels(gene_labels, fontstyle="italic", fontsize=_multi_font(4.2, scale))
    ax0.set_xticks(np.arange(len(labels)))
    ax0.set_xticklabels(labels, rotation=45, ha="right", fontsize=_multi_font(4.4, scale))
    ax0.tick_params(length=0)
    ax0.set_title("A  Brain9 adjusted RNA log fold change", loc="left", fontsize=_multi_font(5.2, scale), fontweight="bold", pad=2 * scale)
    for boundary in (7.5,):
        ax0.axvline(boundary, color="black", lw=0.8)
    cbar = fig.colorbar(im, ax=ax0, fraction=0.028, pad=0.012)
    cbar.ax.tick_params(labelsize=_multi_font(4.2, scale), length=1.4 * scale)

    x = pd.to_numeric(ranking["real_consensus_delta"], errors="coerce").to_numpy(dtype=float)
    y_obs = -np.log10(
        pd.to_numeric(ranking["bh_fdr_observed_direction_multi"], errors="coerce").clip(lower=1e-6).to_numpy(dtype=float)
    )
    y_two = -np.log10(
        pd.to_numeric(ranking["bh_fdr_two_sided_multi"], errors="coerce").clip(lower=1e-6).to_numpy(dtype=float)
    )
    marker_one = 13
    marker_two = 22
    rank_color = "#6B6B6B"
    ax1.axhline(-math.log10(0.05), color=GRAY, ls="--", lw=0.5)
    ax1.axvline(0, color=DARK, lw=0.7)
    label_offsets = {
        "RNPEPL1": (0, 9, "center"),
        "TRAF3IP1": (0, 17, "center"),
        "RBFOX1": (0, 9, "center"),
        "AUTS2": (0, 18, "center"),
        "ERVK13-1": (0, 10, "center"),
        "CNTFR": (0, 18, "center"),
        "SPSB4": (0, 10, "center"),
    }
    for idx, row in ranking.iterrows():
        marker = "s" if str(row.get("variant_group_id")) == str(reference_id) else "o"
        row_x = finite_float(row.get("real_consensus_delta"))
        row_y_obs = finite_float(y_obs[idx] if idx < len(y_obs) else None)
        row_y_two = finite_float(y_two[idx] if idx < len(y_two) else None)
        if row_x is None:
            continue
        if row_y_two is not None and row_y_obs is not None:
            ax1.plot([row_x, row_x], [row_y_two, row_y_obs], color="#BBBBBB", lw=0.5, zorder=1)
        if row_y_obs is not None:
            ax1.scatter(
                row_x,
                row_y_obs,
                facecolors="none",
                s=marker_one,
                edgecolor=rank_color,
                linewidth=0.5,
                marker=marker,
                zorder=3,
            )
        if row_y_two is not None:
            ax1.scatter(
                row_x,
                row_y_two,
                c=rank_color,
                edgecolors=DARK,
                s=marker_two,
                linewidth=0.6,
                marker=marker,
                zorder=4,
            )
        fdr = finite_float(row.get("bh_fdr_two_sided_multi"))
        fdr_obs = finite_float(row.get("bh_fdr_observed_direction_multi"))
        if (fdr is not None and fdr <= 0.05) or (fdr_obs is not None and fdr_obs <= 0.05) or str(row.get("variant_group_id")) == str(reference_id):
            y_label = max([v for v in [row_y_obs, row_y_two] if v is not None], default=0.0)
            dx, dy, ha = label_offsets.get(str(row.get("gene_symbol")), (0, 5, "center"))
            text_label = label_by_variant.get(str(row.get("variant_group_id")), str(row.get("gene_symbol")))
            ax1.annotate(
                text_label,
                xy=(row_x, y_label),
                xytext=(dx, dy),
                textcoords="offset points",
                ha=ha,
                va="bottom",
                fontsize=_multi_font(3.0, scale),
                fontstyle="italic",
                rotation=30,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.2},
                clip_on=False,
            )
    finite_x = pd.to_numeric(ranking["real_consensus_delta"], errors="coerce").dropna().to_numpy(dtype=float)
    finite_y = np.array([v for v in np.r_[y_obs, y_two] if np.isfinite(v)], dtype=float)
    if finite_x.size and finite_y.size:
        x_pad = max(0.01, float(np.ptp(finite_x)) * 0.10)
        ax1.set_xlim(float(np.min(finite_x)) - x_pad, float(np.max(finite_x)) + x_pad)
        y_upper = float(np.max(finite_y)) + 1.02
        # A display-only margin keeps FDR=1 markers at y=0 fully visible.
        ax1.set_ylim(-0.04 * y_upper, y_upper)
        ax1.set_yticks([tick for tick in ax1.get_yticks() if 0 <= tick <= y_upper])
    ax1.set_title("B  Consensus effect and FDR", loc="left", fontsize=_multi_font(5.2, scale), fontweight="bold", pad=2 * scale)
    ax1.set_xlabel("Consensus adjusted RNA log fold change", fontsize=_multi_font(5.0, scale))
    ax1.set_ylabel("-log10 FDR", fontsize=_multi_font(5.0, scale), labelpad=0)
    ax1.tick_params(labelsize=_multi_font(4.4, scale), length=1.5 * scale)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.scatter([], [], c=rank_color, edgecolor=DARK, s=marker_two, marker="o", label="two-sided FDR (primary)")
    ax1.scatter([], [], facecolors="none", edgecolors=rank_color, s=marker_one, marker="o", label="observed-direction FDR (exploratory)")
    ax1.scatter([], [], c=rank_color, edgecolor=DARK, s=marker_one, marker="s", label="reference")
    ax1.legend(
        frameon=False,
        fontsize=_multi_font(3.9, scale),
        loc="upper left",
        bbox_to_anchor=(0, -0.16),
        borderaxespad=0,
        handletextpad=0.65,
        borderpad=0.03,
        labelspacing=0.10,
        handlelength=1.4,
    )

    cos = cosine_table.set_index("variant_group_id").reindex(order).reset_index()
    cos_values = pd.to_numeric(cos["brain_cosine_similarity"], errors="coerce").to_numpy(dtype=float)
    y = np.arange(len(cos))
    bar_colors = [
        "#3B231C" if vid == reference_id else ("#2B6CB0" if value >= 0 else "#B7B7B7")
        for vid, value in zip(cos["variant_group_id"].astype(str), cos_values, strict=False)
    ]
    ax2.axvline(0, color=DARK, lw=0.7)
    ax2.barh(y, cos_values, color=bar_colors, height=0.72)
    for index in np.flatnonzero(~np.isfinite(cos_values)):
        ax2.text(0.02, index, "NA (zero norm)", fontsize=_multi_font(4.2, scale), va="center")
    ax2.set_yticks(y)
    cos_labels = [
        label_by_variant.get(str(row.get("variant_group_id")), str(row.get("gene_symbol") or ""))
        for _, row in cos.iterrows()
    ]
    ax2.set_yticklabels(cos_labels, fontstyle="italic", fontsize=_multi_font(4.2, scale))
    ax2.invert_yaxis()
    ax2.set_xlim(-1, 1)
    ax2.set_title(f"C  {ref_gene} cosine", loc="left", fontsize=_multi_font(5.2, scale), fontweight="bold", pad=2 * scale)
    ax2.set_xlabel("Brain tissue cosine similarity", fontsize=_multi_font(5.0, scale))
    ax2.tick_params(labelsize=_multi_font(4.4, scale), length=1.5 * scale)
    ax2.spines[["top", "right"]].set_visible(False)

    fig.subplots_adjust(left=0.074, right=0.982, bottom=0.22, top=0.88, wspace=0.42)
    if provenance_label:
        fig.text(0.074, 0.018, provenance_label, fontsize=_multi_font(4.7, scale), color='#666666', ha='left', va='bottom')
    fig.savefig(out_prefix.with_suffix(".png"), dpi=600)
    fig.savefig(out_prefix.with_suffix(".svg"))
    fig.savefig(out_prefix.with_suffix(".pdf"))
    plt.close(fig)


def write_multi_plot_html(path: Path, svg_path: Path, summary: dict[str, Any], font_size_pt: float | None = None) -> None:
    svg = svg_path.read_text() if svg_path.exists() else "<p>Plot SVG missing.</p>"
    title = escape(str(summary.get("dataset_name") or "Custom multi-variant result"))
    reference_label = escape(str(summary.get("reference_variant_group_id", "")))
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #202124; background: #fff; }}
    .wrap {{ padding: 6px; }}
    .summary {{ margin-bottom: 10px; font-size: 12px; color: #5f6368; }}
    svg {{ width: 100%; height: auto; display: block; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="summary">
      {title} · reference={reference_label} · variants={summary.get("n_variants_completed")}
    </div>
    {svg}
  </div>
</body>
</html>
"""
    write_text(path, html)


def run_multi_variant_job(
    *,
    db_path: str,
    job_id: str,
    payload: dict[str, Any],
    job_dir: str,
    v04_reference_run: str,
    v04_pipeline_dir: str,
    hg38_fasta: str,
    gencode_gtf: str,
) -> None:
    db = Path(db_path)
    root = Path(job_dir)
    results_dir = root / "results"
    try:
        rows = payload.get("rows") or []
        if not isinstance(rows, list) or not rows:
            raise ValueError("multi-variant payload has no rows")
        update_job(
            db,
            job_id,
            status="running",
            stage="write_inputs",
            message="Writing multi-variant normalized input and validation report",
            progress_percent=4,
        )
        root.mkdir(parents=True, exist_ok=True)
        (root / "input").mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(root / "input" / "normalized_input.tsv", sep="\t", index=False)
        write_json(root / "input" / "validation_report.json", payload.get("validation") or {})
        write_json(root / "input" / "run_config.json", payload)

        single_results: list[dict[str, Any]] = []
        manifest_path = root / "input" / "subjob_manifest.json"
        total = len(rows)
        analysis_mode = str(payload.get("analysis_mode") or "custom_api_exploratory")
        if not analysis_mode.startswith("custom_api"):
            raise ValueError(f"unsupported multi-variant analysis_mode: {analysis_mode}")
        subjob_manifest: list[dict[str, Any]] = []
        for manifest_idx, manifest_row in enumerate(rows, start=1):
            manifest_variant_group_id = safe_id(manifest_row.get("variant_group_id"), f"variant_{manifest_idx}")
            subjob_manifest.append(
                {
                    "row_index": manifest_idx,
                    "variant_group_id": manifest_variant_group_id,
                    "single_job_id": f"{job_id}_{manifest_idx:02d}",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Waiting for earlier variants",
                    "progress_percent": 0.0,
                }
            )
        write_json(manifest_path, {"subjobs": subjob_manifest, "total_variants": total})
        for idx, row in enumerate(rows, start=1):
            variant_group_id = safe_id(row.get("variant_group_id"), f"variant_{idx}")
            sub_job_id = f"{job_id}_{idx:02d}"
            sub_dir = root / "single_variant_jobs" / f"{idx:02d}_{variant_group_id}"
            progress = 6 + (idx - 1) / max(total, 1) * 82
            update_job(
                db,
                job_id,
                stage="api_full",
                message=f"Running variant {idx}/{total}: {variant_group_id}",
                progress_percent=progress,
            )
            single_payload = dict(row)
            single_payload["run_mode"] = "api_full"
            single_payload["analysis_mode"] = "custom_api_local_brain9"
            single_payload["classification_version"] = CLASSIFICATION_VERSION
            manifest_entry = subjob_manifest[idx - 1]
            manifest_entry.update(
                {
                    "status": "submitted",
                    "stage": "submitted",
                    "message": "Queued for single-variant worker",
                    "progress_percent": 2.0,
                }
            )
            write_json(manifest_path, {"subjobs": subjob_manifest, "total_variants": total})
            create_job(
                db,
                job_id=sub_job_id,
                run_mode="api_full",
                input_payload=single_payload,
                job_dir=sub_dir,
            )
            run_job(
                db_path=str(db),
                job_id=sub_job_id,
                payload=single_payload,
                run_mode="api_full",
                job_dir=str(sub_dir),
                v04_reference_run=v04_reference_run,
                v04_pipeline_dir=v04_pipeline_dir,
                hg38_fasta=hg38_fasta,
                gencode_gtf=gencode_gtf,
            )
            sub_job = get_job(db, sub_job_id)
            manifest_entry.update(
                {
                    "status": sub_job.get("status") if sub_job else "missing",
                    "stage": sub_job.get("stage") if sub_job else "missing",
                    "message": sub_job.get("message") if sub_job else "missing",
                    "progress_percent": sub_job.get("progress_percent") if sub_job else 100,
                }
            )
            write_json(manifest_path, {"subjobs": subjob_manifest, "total_variants": total})
            if sub_job and sub_job.get("status") == "complete":
                single_results.append(load_single_result(sub_job))

        write_json(manifest_path, {"subjobs": subjob_manifest, "total_variants": total})
        if not single_results:
            raise RuntimeError("no variants completed successfully; multi-variant result was not generated")
        if len(single_results) != total:
            raise RuntimeError(f"Only {len(single_results)}/{total} variants completed. Cohort BH/cosine withheld; successful single-variant artifacts are preserved.")
        update_job(
            db,
            job_id,
            stage="summarize",
            message=f"Combining {len(single_results)}/{total} completed single-variant outputs",
            progress_percent=90,
        )
        summary = combine_single_results(
            job_id=job_id,
            payload=payload,
            single_results=single_results,
            results_dir=results_dir,
        )
        result = {
            "job_dir": str(root),
            "plot_html": str(results_dir / "multi_variant_plot.html"),
            "plot_png": str(results_dir / "multi_variant_plot.png"),
            "plot_svg": str(results_dir / "multi_variant_plot.svg"),
            "plot_pdf": str(results_dir / "multi_variant_plot.pdf"),
            "source_table": str(results_dir / "source_table.tsv"),
            "group_summary": str(results_dir / "multi_group_matrix.tsv"),
            "consensus_summary": str(results_dir / "multi_consensus_summary.json"),
            "qc_summary": str(results_dir / "qc_summary.md"),
            "multi_matrix": str(results_dir / "multi_group_matrix.tsv"),
            "multi_ranking": str(results_dir / "multi_consensus_ranking.tsv"),
            "multi_cosine": str(results_dir / "multi_reference_cosine.tsv"),
            "normalized_input": str(root / "input" / "normalized_input.tsv"),
            "validation_report": str(root / "input" / "validation_report.json"),
            "subjob_manifest": str(root / "input" / "subjob_manifest.json"),
        }
        update_job(
            db,
            job_id,
            status="complete",
            stage="complete",
            message=f"Multi-variant job complete: {summary['n_variants_completed']}/{summary['n_variants_requested']} variants combined",
            result=result,
            progress_percent=100,
        )
    except Exception as exc:  # noqa: BLE001
        write_text(root / "logs" / "error.txt", f"{type(exc).__name__}: {exc}\n")
        update_job(
            db,
            job_id,
            status="failed",
            stage="failed",
            message=f"{type(exc).__name__}: {exc}",
            progress_percent=100,
        )
