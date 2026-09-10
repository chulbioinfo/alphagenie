"""Read-only v0.23 explorer. Rendering uses only the sealed v0.20 release.

Local job authorization and downloads live in alphagenie/server.py.
This module must not import workers, job stores or an AlphaGenome API client.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app import manuscript_release as release, manuscript_view as view

STATIC_ROOT = Path(__file__).resolve().parent / 'static/v021'
READ_HEADERS = {
    'Cache-Control': 'no-store',
    'X-AlphaGENIE-UI-Version': 'v0.23',
    'X-AlphaGENIE-Data-Version': 'v0.20',
    'X-AlphaGENIE-Inference': 'none',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'none'; object-src 'none'; frame-ancestors 'self'; base-uri 'self'; form-action 'none'",
}


def require_release():
    if not release.ENABLED:
        raise HTTPException(503, 'The saved manuscript release is unavailable.')
    release.manifest()


router = APIRouter(prefix='/api/explorer', dependencies=[Depends(require_release)])


@router.get('/tracks')
def tracks():
    return release.tissue_payload()


@router.get('/{key}')
def dataset(key: str):
    key = release.preset_key(key)
    result = {'result': release.payload(key)}
    if key != 'ccg17':
        result['plot'] = view.point_payload(key)
    return result


def figure_options(figure_width_mm: float = 174, font_size_pt: float = 6.5,
                   top_panel_height_mm: float = 64, effect_panel_height_mm: float = 68):
    return view.options(figure_width_mm, font_size_pt, top_panel_height_mm, effect_panel_height_mm)


@router.get('/{key}/curve.svg')
def curve(key: str):
    key = release.preset_key(key, single=True)
    options = view.options(240, 10.5, 85, 90)
    return Response(view.render(key, options, 'svg', top_only=True), media_type='image/svg+xml')


@router.get('/{key}/view-options')
def validate_options(key: str, options=Depends(figure_options)):
    key = release.preset_key(key, single=True)
    view.render(key, options, 'svg')
    return {**view.asdict(options), 'height_mm': options.height_mm, 'new_inference': False}


@router.get('/{key}/export/{kind}')
def export(key: str, kind: str, options=Depends(figure_options)):
    key = release.preset_key(key, single=True)
    if kind not in {'pdf', 'svg', 'png'}:
        raise HTTPException(404, 'Unknown export format')
    content = view.render(key, options, kind)
    filename = f'{key.upper()}_v020_stacked_{options.width_mm:g}x{options.height_mm:g}mm.{kind}'
    return Response(content, media_type={'pdf': 'application/pdf', 'svg': 'image/svg+xml', 'png': 'image/png'}[kind],
                    headers={'Content-Disposition': f'attachment; filename="{filename}"',
                             'Link': '</static/v021/usage-notice.txt>; rel="describedby"; type="text/plain"'})
