"""Interactive/stacked render-only views of hash-verified v0.20 source assets.

No inference, legacy loaders, score computation, disk exports or source mutation.
The original paired manuscript PDFs remain separate immutable downloads.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from functools import lru_cache
import hashlib
from html import escape
import io
import json
import math
from pathlib import Path
import threading
from urllib.parse import urlencode

from fastapi import HTTPException
import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator, FuncFormatter
import numpy as np

from app import manuscript_release as release

VERSION = 'interactive_stacked_v020_20260910_1'
POS, NEG, ALT = '#b2182b', '#2166ac', '#d820c8'
SHORT = ('Cortex', 'Hipp.', 'BG/Str.', 'Amyg.', 'Dien.', 'Midbr.', 'Cereb.',
         'Whole brain', 'Embryo', 'Non-brain', 'Cells/lines')
SOURCE_NAMES = ('payload.json', 'source_table.tsv', 'group_summary.tsv', 'plot_arrays.npz',
                'frontal_cortex_prediction_status.json', 'gene_model.tsv')
RENDER_LOCK = threading.RLock()


@dataclass(frozen=True)
class Options:
    width_mm: float = 174
    font_size_pt: float = 6.5
    top_panel_height_mm: float = 64
    effect_panel_height_mm: float = 68

    @property
    def height_mm(self):
        return self.top_panel_height_mm + self.effect_panel_height_mm + 4

    @property
    def query(self):
        return urlencode({'figure_width_mm': self.width_mm, 'font_size_pt': self.font_size_pt,
                          'top_panel_height_mm': self.top_panel_height_mm,
                          'effect_panel_height_mm': self.effect_panel_height_mm})


def options(width=None, font=None, top=None, effect=None):
    values = []
    for label, value, default, lower, upper in (
        ('Width', width, 174, 90, 300), ('Font size', font, 6.5, 6, 14),
        ('Top panel height', top, 64, 45, 200), ('Effect panel height', effect, 68, 50, 200),
    ):
        value = float(default if value is None else value)
        if not math.isfinite(value) or not lower <= value <= upper:
            raise HTTPException(422, f'{label} must be between {lower} and {upper}.')
        values.append(round(value, 1))
    result = Options(*values)
    if result.top_panel_height_mm < 28 + 4 * result.font_size_pt:
        raise HTTPException(422, 'Increase top panel height for this font size (at least 28 + 4 x font size mm).')
    if result.effect_panel_height_mm < 28 + 4 * result.font_size_pt:
        raise HTTPException(422, 'Increase effect panel height for this font size (at least 28 + 4 x font size mm).')
    return result


def color(value):
    return POS if value > 0 else NEG if value < 0 else '#bdbdbd'


def verified_context(key):
    key = release.preset_key(key, single=True)
    # Recheck even on a rendering-cache hit. A changed sealed input fails closed.
    paths = tuple(release.asset(f'{key}/{name}') for name in SOURCE_NAMES)
    fingerprint = hashlib.sha256(''.join(release.manifest()['files'][f'{key}/{n}']
                                        for n in SOURCE_NAMES).encode()).hexdigest()
    return _load_context(key, fingerprint, paths)


@lru_cache(maxsize=2)
def _load_context(key, fingerprint, paths):
    files = dict(zip(SOURCE_NAMES, paths))
    result = json.loads(files['payload.json'].read_text())
    status = json.loads(files['frontal_cortex_prediction_status.json'].read_text())
    def rows(name):
        with files[name].open(newline='') as handle:
            return list(csv.DictReader(handle, delimiter='\t'))
    source = rows('source_table.tsv')
    summaries = {r['display_group']: r for r in rows('group_summary.tsv')}
    groups = []
    for i, g in enumerate(result['groups']):
        row = summaries[g['label']]
        groups.append({'x': i, 'display_group': g['label'], 'label': SHORT[i],
                       'n_tracks': int(row['n_tracks']), 'median_effect': float(row['median_effect']),
                       'included_in_brain9': bool(g['included_in_brain9'])})
    group_index = {g['display_group']: g['x'] for g in groups}
    points = []
    for row in source:
        i = group_index[row['display_group']]
        h = int(hashlib.sha256(row['track_key'].encode()).hexdigest()[:8], 16)
        jitter = ((h % 1001) / 1000 - .5) * (.44 if i < 9 else .62)
        point = {name: row.get(name, '') for name in
                 ('track_key', 'track_name', 'biosample_name', 'biosample_type', 'biosample_life_stage',
                  'ontology_curie', 'data_source', 'gtex_tissue', 'display_group', 'track_scope')}
        point.update({name: float(row[name]) for name in ('effect', 'raw_score', 'null_median')})
        point.update(x=i + jitter, group_x=i, included_in_brain9=i < 9)
        if not all(math.isfinite(point[n]) for n in ('effect', 'raw_score', 'null_median')):
            raise RuntimeError('Non-finite manuscript track score')
        points.append(point)
    assert len(points) == len({p['track_key'] for p in points}) == 371
    assert [sum(p['group_x'] == g['x'] for p in points) for g in groups] == [g['n_tracks'] for g in groups]
    assert [g['n_tracks'] for g in groups] == [4, 1, 3, 1, 1, 1, 2, 1, 7, 153, 197]
    with np.load(files['plot_arrays.npz'], allow_pickle=False) as archive:
        curve = {n: archive[n].copy() for n in archive.files}
    for v in curve.values():
        v.setflags(write=False)
    np.testing.assert_allclose(curve['delta'], curve['alternate'] - curve['reference'], equal_nan=True)
    assert status['ontology_curie'] == 'UBERON:0001870'
    assert status['track_metadata']['gtex_tissue'] == 'Brain_Cortex'
    bound = max(abs(p['effect']) for p in points) * 1.14
    return {'key': key, 'fingerprint': fingerprint, 'result': result, 'status': status,
            'groups': groups, 'points': points, 'curve': curve, 'gene': rows('gene_model.tsv'),
            'y_min': -bound, 'y_max': bound}


def point_payload(key):
    c = verified_context(key)
    return {k: c[k] for k in ('groups', 'points', 'y_min', 'y_max')} | {
        'data_version': 'v0.20', 'n_tracks': 371, 'n_null': 1000,
        'endpoint': 'brain9_adult8_embryo', 'source_fingerprint': c['fingerprint']}


def web_payload(frozen):
    """Only presentation metadata changes; frozen statistics/data are preserved."""
    key = release.preset_key(frozen['preset_id'], single=True)
    downloads = dict(frozen['downloads'])
    for ext in ('pdf', 'svg', 'png'):
        downloads[f'manuscript_{ext}'] = downloads[f'plot_{ext}']
        downloads[f'plot_{ext}'] = f'/api/single-variant/preset/{key}/download/plot_{ext}'
    return frozen | {'plot_options_locked': False,
        'plot_options_note': 'Only stacked figure layout is configurable. Scores and original manuscript files remain frozen.',
        'web_view': {'renderer': VERSION, 'layout': 'interactive-stacked', 'n_interactive_points': 371,
                     'export_defaults': asdict(Options()), 'new_inference': False}, 'downloads': downloads}


def _text(fig, width, height, x, y, value, font, **kwargs):
    return fig.text(x / width, y / height, value, fontsize=font, fontfamily='Arial', **kwargs)


def _axis(fig, width, height, x, y, w, h):
    return fig.add_axes([x / width, y / height, w / width, h / height])


def _ticks(ax, which='y', count=4):
    lo, hi = ax.get_ylim() if which == 'y' else ax.get_xlim()
    ticks = MaxNLocator(count).tick_values(lo, hi)
    (ax.set_yticks if which == 'y' else ax.set_xticks)(ticks[(ticks >= lo) & (ticks <= hi)])


def draw_top(fig, c, opt, canvas_height, bottom=0):
    """Use already aligned extrema-preserving arrays; never reproject or resample."""
    w, h, f = opt.width_mm, opt.top_panel_height_mm, opt.font_size_pt
    left, right = 9 + 1.2 * f, 5
    aw = w - left - right
    axis = lambda y, ah: _axis(fig, w, canvas_height, left, bottom + y, aw, ah)
    txt = lambda y, s, **kw: _text(fig, w, canvas_height, left, bottom + y, s, f, **kw)
    a = c['result']['analysis']; v = c['result']['variant']; status = c['status']; z = c['curve']
    line = f * 25.4 / 72 * 1.3
    txt(h - line - 1, f"{v['gene_symbol']} | {a['sequence_length']:,}-bp input | v0.20", weight='bold')
    gene_y = h - line * 2 - 5
    ag = axis(gene_y, 5)
    transcript = status['selected_transcript_name'] + (' (partial)' if status['gene_model_partial'] else '')
    txt(gene_y - line, transcript + (' | 89.5-kb gene view' if c['key'] == 'ptchd1' else ''), style='italic')
    pred_top = gene_y - line * 3
    delta_bottom = line * 3.4
    gap = line * 2
    plot_h = (pred_top - gap - delta_bottom) / 2
    ap = axis(delta_bottom + plot_h + gap, plot_h)
    ad = axis(delta_bottom, plot_h)
    txt(pred_top + line * .7, 'Frontal cortex | UBERON:0001870', weight='bold')
    start, end = status['display_interval_0based_halfopen']
    xmin, xmax = (start + 1) / 1e6, end / 1e6
    x = (z['positions_0based'] + 1) / 1e6
    ref, alt, delta = z['reference'], z['alternate'], z['delta']
    for ax in (ag, ap, ad):
        ax.set_xlim(xmin, xmax)
    ag.set_ylim(0, 1); ag.axis('off')
    gene = next(g for g in c['gene'] if g['feature'] == 'gene')
    lo, hi = max(start, int(gene['start'])), min(end, int(gene['end']))
    ag.hlines(.42, (lo + 1) / 1e6, hi / 1e6, color='#111', lw=.85)
    min_width = (xmax - xmin) * (.5 / (aw * 72 / 25.4))
    for row in c['gene']:
        if row['feature'] != 'exon':
            continue
        l, r = max(start, int(row['start'])), min(end, int(row['end']))
        if r <= l:
            continue
        mid = (l + 1 + r) / 2e6
        ew = max((r - l) / 1e6, min_width)
        ag.add_patch(Rectangle((mid - ew / 2, .25), ew, .34, color='#111', lw=.4))
    for loc in np.linspace((lo + 1) / 1e6, hi / 1e6, 6)[1:-1]:
        dx = (xmax - xmin) * .013 * (1 if gene['strand'] == '+' else -1)
        ag.annotate('', xy=(loc + dx, .42), xytext=(loc - dx, .42),
                    arrowprops={'arrowstyle': '->', 'lw': .6, 'mutation_scale': 6, 'color': '#111'})
    ag.axvline(v['pos1'] / 1e6, ymin=.12, ymax=.75, color=ALT, lw=.6)
    ap.fill_between(x, 0, ref, color='#555', alpha=.18, lw=0)
    ap.plot(x, ref, color='#222', lw=.55, label='REF')
    ap.plot(x, alt, color=ALT, lw=.55, label='ALT')
    ap.set_ylim(0, max(np.nanmax(z['full_reference']), np.nanmax(z['full_alternate'])) * 1.12)
    ap.set_ylabel('RNA\nprediction', fontsize=f, labelpad=3)
    ap.legend(fontsize=f, frameon=False, loc='lower right', bbox_to_anchor=(1, 1.01),
              ncol=2, borderpad=0, borderaxespad=0, handlelength=1.4)
    ap.tick_params(axis='x', bottom=False, labelbottom=False)
    _ticks(ap, count=3)
    ap.yaxis.set_major_formatter(FuncFormatter(lambda val, _: f'{val:.2g}'))
    ad.axhline(0, color='#333', lw=.5)
    ad.fill_between(x, 0, delta, where=delta >= 0, color=POS, alpha=.6, lw=0)
    ad.fill_between(x, 0, delta, where=delta < 0, color=NEG, alpha=.6, lw=0)
    ad.plot(x, delta, color='#555', lw=.45, alpha=.7)
    full_delta = z['full_delta']
    extreme = max(float(np.nanmax(abs(full_delta))), 1e-6)
    threshold = max(float(np.nanquantile(abs(full_delta), .99)), 1e-6)
    ad.set_yscale('symlog', linthresh=threshold)
    ad.set_ylim(-extreme * 1.12, extreme * 1.12)
    ad.set_yticks([-extreme, 0, extreme], labels=[f'{-extreme:.2g}', '0', f'{extreme:.2g}'])
    ad.minorticks_off()
    ad.set_ylabel('Delta RNA', fontsize=f, labelpad=3)
    txt(delta_bottom + plot_h + line * .65, 'ALT - REF (reference-aligned; symlog)')
    _ticks(ad, 'x', 5)
    ad.xaxis.set_major_formatter(FuncFormatter(lambda val, _: f'{val:.3f}' if xmax - xmin < .08 else f'{val:.2f}'))
    ad.set_xlabel(f"{v['chrom']} (Mb, 1-based)", fontsize=f, labelpad=2)
    for ax in (ap, ad):
        ax.axvline(v['pos1'] / 1e6, color=ALT, lw=.6)
        ax.spines[['top', 'right']].set_visible(False)
        ax.tick_params(axis='both', labelsize=f, length=2, pad=2)
        ax.grid(axis='y', color='#dfe4e9', lw=.45)


def draw_effect(fig, c, opt, canvas_height):
    w, h, f = opt.width_mm, opt.effect_panel_height_mm, opt.font_size_pt
    left, right = 9 + 1.2 * f, 5
    line = f * 25.4 / 72 * 1.35
    a = c['result']['analysis']
    txt = lambda y, text, **kw: _text(fig, w, canvas_height, left, y, text, f, **kw)
    txt(h - line - 1, 'Matched-null-adjusted RNA score | 11 categories', weight='bold')
    txt(h - line * 2 - 1, f"Brain9 = {a['real_consensus_delta']:+.5f}; two-sided P = {a['empirical_p_two_sided']:.4f}")
    txt(h - line * 3 - 1, f"Direction-selected P = {a['empirical_p_observed_direction']:.4f} (exploratory)")
    plot_bottom = 9 + f * 2.35
    plot_top = h - line * 5 - 1
    ax = _axis(fig, w, canvas_height, left, plot_bottom, w - left - right, plot_top - plot_bottom)
    medians = [g['median_effect'] for g in c['groups']]
    ax.bar(range(11), medians, width=.75, color=[color(v) for v in medians],
           edgecolor='#222', lw=.5, alpha=.86, zorder=2)
    for p in c['points']:
        ax.scatter(p['x'], p['effect'], s=max(3.3, f * .65) if p['group_x'] < 9 else max(1.8, f * .4),
                   color=color(p['effect']), alpha=.68 if p['group_x'] < 9 else .45, linewidths=0, zorder=4)
    ax.axhline(0, color='#222', lw=.6)
    for b in (7.5, 8.5, 9.5):
        ax.axvline(b, color='#aaa', lw=.45)
    ax.set_xlim(-.5, 10.5); ax.set_ylim(c['y_min'], c['y_max'])
    _ticks(ax)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:.2g}'))
    ax.set_xticks(range(11), labels=[f"{g['label']} ({g['n_tracks']})" for g in c['groups']],
                  rotation=55, ha='right', fontsize=f)
    ax.set_ylabel('Adjusted RNA score', fontsize=f, labelpad=3)
    ax.tick_params(axis='y', labelsize=f, length=2, pad=2)
    ax.tick_params(axis='x', length=0, pad=2)
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='y', color='#dfe4e9', lw=.45); ax.set_axisbelow(True)
    # Short section labels retain room for the one-category pools at print size.
    sections = [(3.5, 'Adult brain'), (8, 'Embryo')]
    if (w - left - right) / 11 >= f * 1.15:
        sections += [(9, 'Tissues'), (10, 'Cells')]
    for x, label in sections:
        ax.text(x, 1.025, label, transform=ax.get_xaxis_transform(), ha='center', va='bottom', fontsize=f)
    txt(4 + line, 'Bars: medians; dots: 371 assay tracks, not replicates.')
    txt(4, 'Brain9: 8 adult bins + Embryo; 1,000 nulls; pools excluded.')


def _figure_bytes(c, opt, kind, *, top_only=False):
    height = opt.top_panel_height_mm if top_only else opt.height_mm
    with RENDER_LOCK, matplotlib.rc_context({'font.family': 'Arial', 'font.size': opt.font_size_pt,
            'pdf.fonttype': 42, 'svg.fonttype': 'none', 'axes.linewidth': .55,
            'path.simplify': False, 'svg.hashsalt': VERSION}):
        fig = Figure(figsize=(opt.width_mm / 25.4, height / 25.4), facecolor='white')
        FigureCanvasAgg(fig)
        draw_top(fig, c, opt, height, 0 if top_only else opt.effect_panel_height_mm + 4)
        if not top_only:
            draw_effect(fig, c, opt, height)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        texts = list(fig.texts)
        for ax in fig.axes:
            texts += list(ax.texts)
            if ax.axison:
                texts += ax.get_xticklabels() + ax.get_yticklabels() + [ax.xaxis.label, ax.yaxis.label]
                labels = [t.get_window_extent(renderer) for t in ax.get_yticklabels() if t.get_visible() and t.get_text()]
                if any(a.overlaps(b) for i, a in enumerate(labels) for b in labels[i + 1:]):
                    raise HTTPException(422, 'Increase panel height to separate axis labels at this font size.')
            legend = ax.get_legend()
            if legend:
                texts += legend.get_texts()
                bounds = legend.get_window_extent(renderer)
                if any(bounds.overlaps(t.get_window_extent(renderer)) for t in fig.texts):
                    raise HTTPException(422, 'Increase width or reduce font size to separate the curve heading and legend.')
        for text in texts:
            if text.get_visible() and text.get_text():
                box = text.get_window_extent(renderer)
                if box.x0 < -1 or box.y0 < -1 or box.x1 > fig.bbox.width + 1 or box.y1 > fig.bbox.height + 1:
                    raise HTTPException(422, 'Labels do not fit this size. Increase width/panel height or reduce font size.')
        output = io.BytesIO()
        metadata = {'Creator': 'Alpha-GENIE v0.20 render-only', 'Title': f"{c['result']['variant']['gene_symbol']} stacked v0.20"}
        if kind == 'png':
            metadata = None
        fig.savefig(output, format=kind, dpi=300, metadata=metadata)
        fig.clear()
        return output.getvalue()


@lru_cache(maxsize=12)
def _render_cached(key, fingerprint, opt, kind, top_only):
    return _figure_bytes(verified_context(key), opt, kind, top_only=top_only)


def render(key, opt, kind='pdf', *, top_only=False):
    if kind not in ('pdf', 'svg', 'png'):
        raise HTTPException(404, 'Unknown export format')
    c = verified_context(key)
    return _render_cached(c['key'], c['fingerprint'], opt, kind, top_only)


def plot_html(key, opt):
    c = verified_context(key)
    # Generating only a small, top-panel SVG keeps interaction independent of PDFs.
    prediction_svg = render(key, opt, 'svg', top_only=True).decode()
    prediction_svg = prediction_svg[prediction_svg.index('<svg'):]
    data = point_payload(key) | {'options': asdict(opt), 'height_mm': opt.height_mm,
                                'preset': c['key'], 'renderer': VERSION}
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    title = escape(c['result']['dataset_label'])
    links = ' '.join(f'<a href="/api/single-variant/preset/{c["key"]}/download/plot_{ext}?{escape(opt.query, quote=True)}">{ext.upper()}</a>'
                     for ext in ('pdf', 'svg', 'png'))
    fixed = f'/api/manuscript/figures/{c["key"]}/figure.pdf'
    template = (Path(__file__).parent / 'templates/manuscript_single.html').read_text()
    for name, value in {'TITLE': title, 'CURVE': prediction_svg, 'PAYLOAD': payload, 'DOWNLOADS': links,
                         'FIXED_PDF': fixed, 'WIDTH': f'{opt.width_mm:g}', 'HEIGHT': f'{opt.height_mm:g}',
                         'FONT': f'{opt.font_size_pt:g}'}.items():
        template = template.replace('@@' + name + '@@', value)
    return template
