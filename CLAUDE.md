# CardCreditsCatalog: notes for Claude

Public repo `valentine242/CardCreditsCatalog`, served by GitHub Pages from `main` (root). It holds the Card Credits app's catalog, privacy and support pages, and the weekly job that updates the catalog. The owner is not a programmer: explain simply, give click-by-click steps. The app itself lives in `~/Developer/CardCredits` (another repo; never edit it from here).

## What lives where
- `catalog.json`, `privacy.html`, `support.html`: the three URLs the app has hard-coded. Never rename or move them. `index.html` links them; `.nojekyll` keeps Pages from processing files.
- `sources.json`: `{id, name, issuer, urls[]}` for 15 cards. Issuer sites only (`config.ALLOWED_HOSTS`).
- `schema/catalog.schema.json`: the catalog's JSON Schema (used by the job, the tests and both workflows). The app decodes exactly this shape; changing it means changing the app.
- `job/config.py`: every setting, including the one model constant `CLAUDE_MODEL`.
- `job/fetch.py`: page text. Plain download plus headless Chromium (Playwright), lines merged; `method` is plain / plain+browser / browser / none.
- `job/extract.py`: the Claude call (structured output, `output_config.format`) and `ground()`, which rejects any benefit whose quote isn't on the page or whose amount isn't in its quote.
- `job/merge.py`: stable ids (match by id, then normalised name, then a new slug; never renumber, never delete: missing benefits become `status: "removed"`).
- `job/classify.py`: safe vs big. `job/report.py`: the pull request table. `job/publish.py`: commit to main (safe) or pull request labelled `needs review` on branch `catalog-update` (big). `job/update.py`: the run. `job/validate.py`: schema check.
- `.github/workflows/update-catalog.yml` (Mondays 10:00 UTC + Run workflow), `tests.yml` (every push and PR).

## Commands
```
python3 -m venv .venv && .venv/bin/pip install -r job/requirements.txt
.venv/bin/python -m pytest -q                 # tests: no network, fake Claude
.venv/bin/python -m job.validate catalog.json
.venv/bin/python -m playwright install chromium
.venv/bin/python -m job.update --check-pages  # which source pages give text (no API key needed)
.venv/bin/python -m job.update                # needs ANTHROPIC_API_KEY; writes catalog.json
.venv/bin/python -m job.publish               # commit to main, or open the pull request
```

## Rules
- Facts come only from issuer pages. Never type a benefit, amount, deadline or term into `catalog.json` by hand or from memory; never guess. An amount not on the page is `value_usd: null` with an empty `value_text`.
- Never merge a catalog pull request: merging is the owner's approval.
- Never write or push a catalog that fails validation.
- Benefit ids are permanent. Nothing is deleted from the catalog (`status: "removed"`).
- Every category is one of the nine in the schema; there is no "Other".
- Every page says: "Not financial advice. Always confirm terms with your card issuer."
- No secrets and no personal data in this public repo (owner name "Valentine Chan" and the support address only). The API key lives only in the `ANTHROPIC_API_KEY` repository secret.
- Pages: plain HTML with an inline stylesheet (light and dark); no external assets, scripts or trackers.
- Fix problems at their cause. Add a test for every change to classify, merge, ground or the schema.
- Run the tests before every commit; push after each commit.
