# GitHub publishing checklist

This folder is a standalone Git repository candidate. No remote repository, push, live deployment or public policy approval is assumed.

## Before public release

- [ ] Owner selects a code license and replaces `LICENSE`; confirms contributor/copyright rights.
- [ ] Owner confirms bundled manuscript outputs can be publicly redistributed under the applicable provider/output terms and manuscript policy. Remove them if not authorized, and change the viewer packaging contract explicitly rather than silently breaking it.
- [ ] Configure repository owner/name, private vulnerability reporting, issue templates and maintainers. No fake author/contact/DOI is supplied.
- [ ] Test a clean install on supported platforms. The exact dependency snapshot is not a platform-independent hash lock.
- [ ] Using your own eligible key, explicitly run a 10-null smoke test and then the intended 1,000-null single/multi analyses. Review raw-score provenance and null completeness. Development did not spend API quota to do this.
- [ ] Read `docs/METHODS.md`: fresh Brain9 scores and Frontal cortex curves use the manuscript grouping/track but are not the saved inference; review the strict catalog contract in `docs/BRAIN9.md`.
- [ ] Run tests and the release scanner; inspect the staged diff and every file to be published. Never include personal `.alphagenie`, `.env`, raw jobs, references or credentials.

- [ ] Keep all distributed prose and code comments in English; run the language guard with the release scanner.

## Local checks

```sh
source .venv/bin/activate
python -m unittest discover -s tests -v
node --test tests/*.mjs
python scripts/release_check.py
git status --short
git diff --cached --stat
git diff --cached
```

The included GitHub Actions workflow runs only offline checks with no API secrets. It does not deploy, infer or publish a release. Enable network/real-key tests only by a separately reviewed, explicit workflow; never put a secret in a pull request job.

## Commit and push after the release gates

If this folder has not yet been initialized, run `git init -b main`. Use your own configured Git identity. The commands below are instructions only; replace `OWNER` with the account/organization you control and create the intended empty GitHub repository first.

```sh
git add README.md README.ko.md LICENSE NOTICE.md SECURITY.md requirements.txt requirements-lock.txt package.json .gitignore .gitattributes .github alphagenie app worker pipeline data docs examples scripts tests SOURCE_ORIGIN.json
git diff --cached --stat
python scripts/release_check.py
git commit -m "Prepare AlphaGENIE local v0.21 interface and v0.20 engine"
git remote add origin https://github.com/OWNER/AlphaGENIE.git
git push -u origin main
```

Do not execute placeholder commands unchanged. A source ZIP can be made with `python scripts/source_archive.py`; this uses an explicit source allowlist and excludes `.git`, virtual environments and runtime state. Verify the resulting archive before attaching it to a release.

Label the first release **pre-release** until real-key and clean-machine gates pass. Include the code commit, dependency versions, saved release identity, methods limitations, privacy statement and Google attribution in release notes.
