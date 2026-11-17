# CardCreditsCatalog: notes for Claude

Public repo `valentine242/CardCreditsCatalog`, served by GitHub Pages from `main` (root). It holds the Card Credits app's catalog, privacy and support pages, and the weekly job that updates the catalog. The owner is not a programmer: explain simply, give click-by-click steps. The app itself lives in `~/Developer/CardCredits` (another repo; never edit it from here).

## What lives where
- `catalog.json`, `privacy.html`, `support.html`: the three URLs the app has hard-coded. Never rename or move them. `index.html` links them; `.nojekyll` keeps Pages from processing files.
- `sources.json`: `{id, name, issuer, short_name?, color?, urls[]}` for 15 cards. Issuer sites only (`config.ALLOWED_HOSTS`). `short_name` and `color` are the card's **display hints** (owner approved Nov 16 2026): how the app names and colours the card, curated here by hand, never extracted by the job.
- `schema/catalog.schema.json`: the catalog's JSON Schema (used by the job, the tests and both workflows). The app decodes exactly this shape; changing it means changing the app.
- `job/config.py`: every setting, including the one model constant `CLAUDE_MODEL`.
- `job/fetch.py`: page text. Plain download plus headless Chromium (Playwright), lines merged; `method` is plain / plain+browser / browser / none.
- `job/extract.py`: the Claude call (structured output, `output_config.format`) and `ground()`, which rejects any benefit whose quote isn't on the page or whose amount isn't in its quote.
- Display hints in the code: `merge.with_display_hints` / `apply_display_hints` copy them from `sources.json` onto every catalog card unchanged (also a card whose page gave nothing; a hint taken out of `sources.json` leaves the catalog); `validate.sources_errors` checks them against the schema before a run; `classify.CARD_DISPLAY_FIELDS` makes a change to either a **safe** change. Tests: `tests/test_display_hints.py`.
- `job/merge.py`: stable ids (match by id, then normalised name, then a new slug; never renumber, never delete: missing benefits become `status: "removed"`).
- `job/classify.py`: safe vs big. `job/report.py`: the pull request table. `job/publish.py`: commit to main (safe) or pull request labelled `needs review` on branch `catalog-update` (big). `job/update.py`: the run. `job/validate.py`: schema check.
- `job/manual.py`: the same run **without the Claude API** (the owner chose not to use an API key, Nov 14 2026). `save-pages` keeps each page's text in `out/pages/`; Claude Code reads them and writes `out/answers/<card id>.json` (the `extract.output_schema()` shape, one list per URL, every benefit with a word-for-word `evidence` quote); `run` sends those answers through `ground`, merge, classify and publish exactly like the weekly job. A page with no answer counts as unread (big), never as empty.
- `.github/workflows/update-catalog.yml` (manual Run workflow only, needs the API key; the weekly schedule is off), `tests.yml` (every push and PR).

## Commands
```
python3 -m venv .venv && .venv/bin/pip install -r job/requirements.txt
.venv/bin/python -m pytest -q                 # tests: no network, fake Claude
.venv/bin/python -m job.validate catalog.json
.venv/bin/python -m playwright install chromium
.venv/bin/python -m job.update --check-pages  # which source pages give text (no API key needed)
.venv/bin/python -m job.update                # needs ANTHROPIC_API_KEY; writes catalog.json
.venv/bin/python -m job.publish               # commit to main, or open the pull request
.venv/bin/python -m job.manual save-pages     # no API key: save every page's text to out/pages/
.venv/bin/python -m job.manual run --publish  # build from out/answers/, then commit or open the PR
```

## Rules
- Facts come only from issuer pages. Never type a benefit, amount, deadline or term into `catalog.json` by hand or from memory; never guess. An amount not on the page is `value_usd: null` with an empty `value_text`.
- Display hints are the one thing typed by hand, and only in `sources.json`. `short_name`: from the card's own official name (drop the issuer, a leading "The", a trailing "Card"; keep a co-brand partner's word; no invented nicknames). `color`: the colour family (`gold`, `platinum`, `silver`, `black`, `blue`, `green`, `red`, `purple`, `white`, `rose`) of the card image on the issuer's own page, or of a metal in the card's name; leave it out when the page doesn't make it clear (today: Delta SkyMiles Reserve, a dark slate grey between black and blue). Never copy an issuer's card artwork into this repo.
- Never merge a catalog pull request: merging is the owner's approval.
- Never write or push a catalog that fails validation.
- Benefit ids are permanent. Nothing is deleted from the catalog (`status: "removed"`).
- Every category is one of the nine in the schema; there is no "Other".
- Every page says: "Not financial advice. Always confirm terms with your card issuer."
- No secrets and no personal data in this public repo (owner name "Valentine Chan" and the support address only). The API key lives only in the `ANTHROPIC_API_KEY` repository secret.
- Pages: plain HTML with an inline stylesheet (light and dark); no external assets, scripts or trackers.
- Fix problems at their cause. Add a test for every change to classify, merge, ground or the schema.
- Run the tests before every commit; push after each commit.

## Running the check without the API (how the owner runs it)
When the owner asks for a catalog check: `save-pages`; read each card's page text (benefit lines with their surroundings); write each card's answer file following the rules in `extract.SYSTEM_PROMPT` (only what the page states, one period window per amount, existing ids matched, nothing from memory); check each file with `ground` before the run; `run --publish`; tell the owner the pull request link and anything left out on purpose. Never merge it.
