# Card Credits Catalog

This is the public website and data file behind the **Card Credits** iPhone app.

- **catalog.json** is the list of cards and their credits. The app downloads it about once a day.
- **privacy.html** and **support.html** are the app's privacy policy and support page.
- The list is checked against the card issuers' own web pages **when you ask Claude Code to**. No API key is used (your choice, Nov 14 2026).

The site lives at https://valentine242.github.io/CardCreditsCatalog/. The app has these three addresses built in, so never rename the files:

| File | Address |
|---|---|
| catalog.json | https://valentine242.github.io/CardCreditsCatalog/catalog.json |
| privacy.html | https://valentine242.github.io/CardCreditsCatalog/privacy.html |
| support.html | https://valentine242.github.io/CardCreditsCatalog/support.html |

Anything pushed to the `main` branch is published on the site a minute or two later.

Not financial advice. Always confirm terms with your card issuer.

## How to check the list (no API key)

About once a month, open Terminal and type:

```
cd ~/Developer/CardCreditsCatalog && claude "Run the catalog check without the API, as in CLAUDE.md."
```

Claude Code reads every issuer page on your own Claude plan, and the same program as below checks each credit it found against the page. Big changes open a pull request for you to review; you merge it to publish. Nothing costs extra.

## How the check works

Each check (by Claude Code, or by the "Update catalog" job if you ever add an API key) does this:

1. It opens each card's official page (listed in `sources.json`; issuer sites only: Chase, American Express, Capital One, Citi).
2. It sends the page's text to Claude (Anthropic's AI) and asks: which credits does this page state? Claude may only use what is written on the page. A program then checks every answer against the page: each credit needs a word-for-word quote from the page, and each dollar amount must be in that quote. Anything that fails is thrown out, not guessed.
3. It compares the result with the current list and sorts every difference into two piles:

| Pile | What's in it | What happens |
|---|---|---|
| **Safe** | A credit's name, setup step or details were reworded; the "last checked" date was refreshed | Published straight away, no action from you |
| **Big** | An amount changed, a credit was added or removed, a new card, a period / category / end date changed, a page couldn't be read, or the result failed its checks | A **pull request** labelled **needs review** is opened. Nothing is published until you merge it |

If a run has both safe and big changes, they all wait together in the pull request, so the app never sees a half-updated list.

A credit that disappears from an issuer's page is never deleted. It stays in the list marked `removed`, so the app can keep people's history for it.

## Optional: make it automatic with an API key

You don't need this. It lets GitHub run the check by itself (it is billed separately from your Claude plan, roughly $2–4 per run). After adding the key, ask Claude Code to turn the weekly schedule back on.

**Get a key**

1. Go to https://console.anthropic.com and sign in (or create an account).
2. Click **Settings** (the gear), then **Billing**, and add a payment method and a little credit. One weekly run reads 15 pages and costs well under a dollar or two.
3. Click **API keys** in the left sidebar.
4. Click **Create Key**. Name it `CardCreditsCatalog`. Click **Create Key** (or **Add**).
5. Click **Copy**. The key starts with `sk-ant-`. You can't see it again after closing the window, so paste it in the next step right away.

**Put it in GitHub**

1. Open https://github.com/valentine242/CardCreditsCatalog
2. Click **Settings** (top row of the repo, far right).
3. In the left sidebar click **Secrets and variables**, then **Actions**.
4. Click **New repository secret**.
5. Name: `ANTHROPIC_API_KEY` (exactly this). Secret: paste the key.
6. Click **Add secret**.

*Terminal alternative:* run this, then paste the key when asked and press Return:

```
gh secret set ANTHROPIC_API_KEY --repo valentine242/CardCreditsCatalog
```

Never paste the key into a file in this folder, an issue or a pull request. This repository is public.

## Run the check yourself

1. Open https://github.com/valentine242/CardCreditsCatalog/actions
2. Click **Update catalog** in the left sidebar.
3. Click **Run workflow** (right side), then the green **Run workflow** button.
4. After a few minutes, click the run to see its summary table.

The **first run** adds six new cards (Capital One Venture X, Citi Strata Elite, Chase Sapphire Preferred, Business Platinum, Delta SkyMiles Platinum, Hilton Honors Surpass). New cards are a big change, so it will open a pull request for you to review.

## Review and merge a "needs review" pull request

1. Open https://github.com/valentine242/CardCreditsCatalog/pulls and click the pull request called "Catalog update …".
2. Read the table at the top. Each row is one change: the card, the benefit, what changed, the old value, the new value and a link to the issuer's page.
3. For each row, click **issuer page** and check that the page really says the new value.
4. Rows named "page yielded nothing", "page could not be read by Claude" or "claim not backed by the page" mean the robot couldn't confirm something. That card's entries were left as they were. Open the page yourself; if the issuer moved the page, its new address goes in `sources.json` (ask Claude Code to do it).
5. Happy with everything? Click **Merge pull request**, then **Confirm merge**. That's your approval; the site updates in a minute or two.
6. Something's wrong? Don't merge. Click **Close pull request**. Nothing is published, and next Monday's check tries again.

A pull request left open is simply refreshed by the next run.

## What's in this folder

| Path | What it is |
|---|---|
| `catalog.json` | The published list (the app reads this) |
| `index.html`, `privacy.html`, `support.html` | The website |
| `sources.json` | The official issuer page(s) for each of the 15 cards |
| `schema/catalog.schema.json` | The exact shape `catalog.json` must have |
| `job/` | The update robot (Python) |
| `tests/` | Its tests (no internet needed) |
| `.github/workflows/` | The update job (manual, needs an API key) and the test run |

## Before the app goes live

- Replace the placeholder support address `cardcredits.support@example.com` in `privacy.html` and `support.html` (one line in each, marked with a comment that says PLACEHOLDER).
