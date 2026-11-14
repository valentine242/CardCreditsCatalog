"""The weekly catalog check.

    python -m job.update                 read the pages, ask Claude, write catalog.json
    python -m job.update --publish       ...then commit to main or open a pull request
    python -m job.update --check-pages   no Claude: just show which pages give text

Needs ANTHROPIC_API_KEY in the environment (not for --check-pages).
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import config, fetch, report
from .classify import BIG, Change, classify, has_big
from .extract import ClaudeExtractor, ExtractionError, FatalExtractionError, ground
from .merge import merge_catalog, normalise_name
from .validate import catalog_errors


@dataclass
class RunResult:
    catalog: dict                       # always valid; equals the old one if nothing was usable
    changes: list[Change] = field(default_factory=list)
    pages: list[fetch.PageText] = field(default_factory=list)

    @property
    def big(self) -> bool:
        return has_big(self.changes)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_catalog(catalog: dict) -> str:
    return json.dumps(catalog, indent=1, ensure_ascii=False) + "\n"


def _problem(kind: str, card: dict, detail: str, url: str = "") -> Change:
    return Change(BIG, kind, card["name"], "", "", detail, url)


def run(catalog: dict, sources: dict, today: str, get_text, extractor) -> RunResult:
    """Read every source page and build the next catalog. Never raises for a
    single bad page: it becomes a "big" row so a person looks at it."""
    problems: list[Change] = []
    pages: list[fetch.PageText] = []
    current = copy.deepcopy(catalog)
    old_cards = {c["id"]: c for c in catalog["cards"]}

    for card in sources["cards"]:
        existing = old_cards.get(card["id"], {}).get("benefits", [])
        found: list[dict] = []
        seen: set[str] = set()
        complete = True

        for url in card["urls"]:
            page = get_text(url)
            pages.append(page)
            if not page.ok:
                complete = False
                problems.append(_problem("page yielded nothing", card,
                                         page.note or "no readable text", url))
                continue
            try:
                raw = extractor.extract(card, url, page.text, existing)
            except FatalExtractionError:
                raise
            except ExtractionError as exc:
                complete = False
                problems.append(_problem("page could not be read by Claude", card, str(exc), url))
                continue
            grounded = ground(raw, page.text, url)
            for reason in grounded.rejected:
                complete = False
                problems.append(_problem("claim not backed by the page (left out)",
                                         card, reason, url))
            if not grounded.benefits and not grounded.rejected:
                complete = False
                problems.append(_problem("page yielded nothing", card,
                                         "no benefits were found in the page text", url))
            for benefit in grounded.benefits:
                key = benefit["existing_id"] or normalise_name(benefit["name"])
                if key not in seen:  # the same benefit on two pages counts once
                    seen.add(key)
                    found.append(benefit)

        if not found:
            continue
        candidate = merge_catalog(
            current, [{"card": card, "found": found, "complete": complete}], today)
        errors = catalog_errors(candidate)
        if errors:
            # Never keep a card that breaks the schema: leave it as it was.
            problems.append(_problem("validation failure (card left unchanged)", card,
                                     "; ".join(errors[:5]), card["urls"][0]))
            continue
        current = candidate

    current["generated"] = today
    current["note"] = config.CATALOG_NOTE
    final_errors = catalog_errors(current)
    if final_errors:
        problems.append(Change(BIG, "validation failure (nothing written)", "(whole catalog)",
                               "", "", "; ".join(final_errors[:5])))
        current = copy.deepcopy(catalog)
    return RunResult(current, classify(catalog, current) + problems, pages)


def check_pages(sources: dict) -> int:
    """No Claude involved: which pages give benefit text, and how."""
    failures = 0
    print(f"{'card':28} {'method':13} {'chars':>7}  url")
    for card in sources["cards"]:
        for url in card["urls"]:
            page = fetch.get_page_text(url)
            failures += not page.ok
            print(f"{card['id']:28} {page.method:13} {len(page.text):>7}  {url}")
            if page.note:
                print(f"{'':28} note: {page.note}")
    print("\nplain = the normal download has it all; plain+browser = the headless "
          "browser added benefit lines;\nbrowser = only the headless browser works; "
          "none = no benefit text (needs a person to look).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Card Credits weekly catalog check")
    parser.add_argument("--publish", action="store_true",
                        help="commit safe changes to main, or open a pull request for big ones")
    parser.add_argument("--check-pages", action="store_true",
                        help="only test which source pages give readable text")
    parser.add_argument("--today", default=datetime.date.today().isoformat(),
                        help="date to stamp (YYYY-MM-DD); default is today")
    args = parser.parse_args(argv)

    sources = load_json(config.SOURCES_PATH)
    if args.check_pages:
        return check_pages(sources)

    catalog = load_json(config.CATALOG_PATH)
    start_errors = catalog_errors(catalog)
    if start_errors:
        print("ERROR: catalog.json is already invalid; fix it before updating:")
        for line in start_errors:
            print(f"  - {line}")
        return 1

    try:
        result = run(catalog, sources, args.today, fetch.get_page_text, ClaudeExtractor())
    except FatalExtractionError as exc:
        print(f"ERROR: {exc}")
        return 1

    summary = report.summary_markdown(result.changes, args.today)
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(summary)

    errors = catalog_errors(result.catalog)
    if errors:  # run() already guarantees this; a second lock on the door
        print("ERROR: refusing to write a catalog that fails validation.")
        return 1
    config.CATALOG_PATH.write_text(dump_catalog(result.catalog), encoding="utf-8")
    print(f"catalog.json written. Needs review: {'yes' if result.big else 'no'}.")
    config.OUT_DIR.mkdir(exist_ok=True)
    (config.OUT_DIR / "summary.md").write_text(summary, encoding="utf-8")
    (config.OUT_DIR / "result.json").write_text(json.dumps({
        "big": result.big,
        "today": args.today,
        "title": report.title(result.changes, args.today),
        "pages": [{"url": p.url, "method": p.method, "note": p.note} for p in result.pages],
    }, indent=1), encoding="utf-8")

    if args.publish:
        from . import publish
        return publish.publish(result.big, report.title(result.changes, args.today),
                               summary, args.today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
