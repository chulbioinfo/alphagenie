# GitHub publishing checklist

This checklist concerns the standalone CLI distribution, not the public website. Its presence does not establish a successful GitHub release, native CI run, deployment or provider approval. Version 0.22.0 is a **research preview / pre-release**, not a stable or open-source release; the current code license remains owner decision pending and all rights reserved unless separately licensed.

## Before public release

- [ ] Owner selects a code license and replaces `LICENSE`; confirms contributor/copyright rights.
- [ ] Owner confirms bundled manuscript outputs can be publicly redistributed under the applicable provider/output terms and manuscript policy. Remove them if not authorized, and change the viewer packaging contract explicitly rather than silently breaking it.
- [ ] Configure repository owner/name, private vulnerability reporting, issue templates and maintainers. No fake author/contact/DOI is supplied.
- [ ] Verify fresh native installs on all supported platforms using the complete hashed runtime and installer locks. A fresh isolated macOS arm64 install and other-platform wheel-resolution dry runs have passed; dry runs do not establish native execution or an independent clean-machine test.
- [ ] Using your own eligible key, explicitly run a 10-null smoke test and then the intended 1,000-null single/multi analyses. Review raw-score provenance and null completeness. Development did not spend API quota to do this.
- [ ] Read `docs/METHODS.md`: fresh Brain9 scores and Frontal cortex curves use the manuscript grouping/track but are not the saved inference; review the strict catalog contract in `docs/BRAIN9.md`.
- [ ] Run tests and the release scanner; inspect the staged diff and every file to be published. Never include personal `.alphagenie`, `.env`, raw jobs, references or credentials.

- [ ] Keep all distributed prose and code comments in English; run the language guard with the release scanner.

## Local checks

```sh
source .venv/bin/activate
python scripts/dependency_check.py --installed --advisories
python scripts/refresh_dependency_lock.py
python -m unittest discover -s tests -v
node --test tests/*.mjs
python scripts/release_check.py
git status --short
git diff --cached --stat
git diff --cached
```

The included GitHub Actions workflow downloads reviewed hashed wheels, queries public dependency advisories and runs offline scientific/security checks without API secrets. It does not deploy, infer or publish a release. Its four-platform configuration is not proof those jobs have completed. Enable real-key tests only by a separately reviewed, explicit workflow; never put a secret in a pull request job.

## Commit and push after the release gates

If this folder has not yet been initialized, run `git init -b main`. Use your own configured Git identity. The commands below are instructions only; replace `OWNER` with the account/organization you control and create the intended empty GitHub repository first.

```sh
git add README.md LICENSE NOTICE.md SECURITY.md requirements.txt requirements-lock.txt requirements-installer.txt package.json .gitignore .gitattributes .github alphagenie app worker pipeline data docs examples scripts tests SOURCE_ORIGIN.json
git diff --cached --stat
python scripts/release_check.py
git commit -m "Prepare AlphaGENIE v0.22 research preview with preserved v0.20 engine"
git remote add origin https://github.com/OWNER/AlphaGENIE.git
git push -u origin main
```

Do not execute placeholder commands unchanged. A source ZIP can be made with `python scripts/source_archive.py`; this uses an explicit source allowlist and excludes `.git`, virtual environments and runtime state. Verify the resulting archive before attaching it to a release.

Label **v0.22.0** as a **research preview / pre-release**. Do not present it as stable until real-key, native-platform and rights gates pass. Include the actual code commit, dependency versions, saved release identity, methods limitations, privacy statement and Google attribution in release notes. Keep the private-computer-only warning prominent: there is no local authentication or isolation against other local users. Use [release notes](RELEASE_NOTES_v0.22.md) as reviewed source text, not proof that publication already happened.
