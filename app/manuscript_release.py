"""Read-only, hash-bound manuscript presets; no inference or legacy fallback."""
from __future__ import annotations

from functools import lru_cache
import hashlib
from html import escape
import json
import os
from pathlib import Path, PurePosixPath

from fastapi import HTTPException

RELEASE_ID = 'alphagenie_manuscript_v020_20260909'
PUBLIC_DATA_VERSION = 'v0.24'
SOURCE_DATA_VERSION = 'v0.20'
VERIFIED_REANALYSIS_EPOCH = 'dc23d1efac044e49a9f162e6561673d7'
VERIFIED_REANALYSIS_COMPLETED_AT = '2026-09-11T02:55:07.771329+00:00'
ROOT = Path(os.environ.get('AG_WEB_MANUSCRIPT_ROOT',
            str(Path(__file__).resolve().parents[1] / 'data/manuscript_v020_20260909')))
ENABLED = os.environ.get('AG_WEB_MANUSCRIPT_ENABLED', '1').lower() not in {'0', 'false', 'no'}
ALIASES = {'rbfox1': 'rbfox1', 'rbfox1_del3': 'rbfox1', 'rbfox1_del3_demo': 'rbfox1',
           'ptchd1': 'ptchd1', 'ptchd1_ins27': 'ptchd1', 'ptchd1_ins27_demo': 'ptchd1',
           'ccg17': 'ccg17', 'ccg20': 'ccg17', 'rbfox1-ccg12': 'ccg17'}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def preset_key(value: str, *, single: bool = False) -> str:
    key = ALIASES.get(value.strip().lower())
    if key is None or (single and key == 'ccg17'):
        raise HTTPException(404, 'Unknown manuscript preset')
    return key


@lru_cache(maxsize=1)
def manifest() -> dict:
    """Validate the complete public asset set on startup, before serving it."""
    source = ROOT / 'manifest.json'
    record = json.loads(source.read_text())
    if (record.get('release_id') != RELEASE_ID or record.get('data_version') != 'v0.20'
            or record.get('validation_passed') is not True
            or record.get('n_variants') != 17 or record.get('n_null_per_variant') != 1000):
        raise RuntimeError('Manuscript release identity/validation is invalid')
    files = record.get('files')
    if not isinstance(files, dict) or not files:
        raise RuntimeError('Manuscript asset hash manifest is missing')
    for relative, expected in files.items():
        pure = PurePosixPath(relative)
        if pure.is_absolute() or '..' in pure.parts or '\\' in relative:
            raise RuntimeError('Invalid manuscript asset path')
        path = (ROOT / relative).resolve(strict=True)
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or digest(path) != expected:
            raise RuntimeError(f'Manuscript artifact failed verification: {relative}')
    required = {'tissue_payload.json'} | {f'{k}/{name}' for k in ('rbfox1', 'ptchd1', 'ccg17')
                                         for name in ('payload.json', 'figure.pdf', 'figure.svg', 'figure.png')}
    if not required.issubset(files):
        raise RuntimeError('Incomplete manuscript preset release')
    actual = {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p != source}
    if actual != set(files):
        raise RuntimeError('Manuscript asset inventory differs from verified manifest')
    return record


def asset(relative: str) -> Path:
    if relative not in manifest()['files']:
        raise HTTPException(404, 'Manuscript file is not in the public download allowlist')
    path = (ROOT / relative).resolve(strict=True)
    if not path.is_relative_to(ROOT.resolve()):
        raise HTTPException(404, 'Invalid manuscript artifact')
    if digest(path) != manifest()['files'][relative]:
        raise HTTPException(503, 'Manuscript artifact failed integrity validation')
    return path


def payload(key: str) -> dict:
    return json.loads(asset(f'{preset_key(key)}/payload.json').read_text())


def tissue_payload() -> dict:
    return json.loads(asset('tissue_payload.json').read_text())


def public_release() -> dict:
    data = manifest()
    return {
        **{k: data[k] for k in ('release_id', 'endpoint', 'n_variants',
                                'n_null_per_variant', 'validation_passed')},
        'data_version': PUBLIC_DATA_VERSION,
        'source_data_version': SOURCE_DATA_VERSION,
        'source_release_id': data['release_id'],
        'served_artifact_source_version': SOURCE_DATA_VERSION,
        'verification_design': 'One fresh provider inference epoch; separate web and GitHub aggregation of the same raw scores; fixed-seed matched-null design.',
        'verified_reanalysis_epoch': VERIFIED_REANALYSIS_EPOCH,
        'verified_reanalysis_completed_at': VERIFIED_REANALYSIS_COMPLETED_AT,
        'verified_reanalysis_status': 'passed',
        'verified_reanalysis_equivalence': (
            '19/19 contexts: raw score, null median, adjusted effect, consensus and '
            'empirical P values reproduced; 17-variant matrix and BH reproduced; '
            'Frontal cortex curves reproduced within serialization precision.'
        ),
    }


def select_cached_variant(submitted: dict) -> dict:
    """A cached submit returns its exact frozen result, never creates an API job."""
    for key in ('rbfox1', 'ptchd1'):
        result = payload(key)
        expected = result['variant']
        if all(str(submitted.get(field, '')).upper() == str(expected.get(field, '')).upper()
               for field in ('chrom', 'pos1', 'ref', 'alt', 'gene_symbol', 'target_gene')):
            if int(submitted.get('sequence_length', 0)) != int(result['analysis']['sequence_length']):
                raise HTTPException(422, 'The cached preset has a fixed input length; select New API run for another length.')
            if int(submitted.get('null_depth', 0)) != 1000:
                raise HTTPException(422, 'The cached manuscript preset contains exactly 1,000 matched nulls.')
            return result
    raise HTTPException(422, 'Cached mode accepts only the exact RBFOX1 16kb or PTCHD1 1Mb manuscript variant.')


def plot_html(key: str) -> str:
    key = preset_key(key, single=True)
    result = payload(key)
    title = escape(result['dataset_label'])
    links = ' '.join(f'<a href="/api/manuscript/figures/{key}/figure.{ext}" download>{ext.upper()}</a>'
                     for ext in ('pdf', 'svg', 'png'))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{margin:0;padding:12px;font:14px Arial,sans-serif;color:#253241;background:white}}
img{{display:block;width:100%;height:auto;min-width:620px}}.figure{{overflow:auto}}a{{margin-right:14px;color:#24578b}}
p{{line-height:1.5;margin:10px 0}}</style></head><body>
<div class="figure"><img src="/api/manuscript/figures/{key}/figure.svg" alt="{title}"></div>
<p>{links}</p><p>Verified v0.20 manuscript figure. Fixed 174 × 78 mm; text ≥6.25 pt.
Frontal cortex UBERON:0001870. Brain9 includes 14 adult tracks in eight categories and seven Embryo tracks.
Standalone empirical P values are not cohort FDR. No new API call.</p></body></html>'''
