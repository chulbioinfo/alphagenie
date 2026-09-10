# Third-party and output notices

- **AlphaGenome**, Google DeepMind: the separately installed [Python API client](https://github.com/google-deepmind/alphagenome) is Apache-2.0 licensed. Its documentation/examples have separate notices. We install it as a dependency; this package does not redistribute model weights or a Google API key.
- AlphaGENIE's original code license is pending owner selection. A permissive code license, if selected, will not override [API terms](https://deepmind.google.com/science/alphagenome/terms) or [output terms](https://deepmind.google.com/science/alphagenome/output-terms).
- Bundled `data/manuscript_v020_20260909/` files are **AlphaGenome-derived scientific outputs**, not relicensed as unrestricted code. Retain their provenance and the [use/modification notice](app/static/v021/usage-notice.txt) when redistributing, and confirm publication/data rights.
- AlphaGENIE modifications comprise matched-null calibration, group assignment, empirical statistics, comparison and visualization. The interface and calibrated outputs are not official Google products and are not endorsed by Google DeepMind.
- Scientific computing and web dependencies (NumPy, pandas, Matplotlib, FastAPI, Uvicorn, Pydantic and transitive packages) retain their respective upstream licenses, installed with those packages.
- No proprietary font files are included. Rendering may substitute available fonts; the sealed original PDFs remain byte-identical, while newly rendered layouts depend on the local environment.
- Attribution: cite the [AlphaGenome paper](https://doi.org/10.1038/s41586-025-10014-0) and the exact AlphaGENIE release/commit used. No AlphaGENIE DOI, author list or public GitHub URL has been invented for this pre-release package.
