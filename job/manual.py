"""Run the update without the Claude API: the benefits come from answer files
a person (or Claude Code, on the owner's own plan) wrote after reading the
saved pages. Everything after extraction is the same as the weekly job: each
benefit's quote must be on the page and its amount in its quote (`ground`),
ids stay stable, missing benefits become "removed", and big changes open a
pull request.

    python -m job.manual save-pages            fetch every source page into out/pages/
    python -m job.manual run --today YYYY-MM-DD   build catalog.json from out/answers/
    python -m job.manual run --publish ...        ...then commit or open the pull request

Answer files: out/answers/<card id>.json =
    {"card": "<card id>", "pages": {"<url>": [<benefit in extract.output_schema() shape>, ...]}}
A page missing from the answer file counts as "could not be read" (big), never as "no benefits".
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from . import config, fetch, report
from .extract import ExtractionError
from .update import dump_catalog, load_json, run
from .validate import catalog_errors

PAGES_DIR = config.OUT_DIR / "pages"
ANSWERS_DIR = config.OUT_DIR / "answers"


def _page_file(card_id: str, index: int) -> str:
    return f"{card_id}-{index}.txt"


def save_pages(sources: dict, folder: Path = PAGES_DIR, get_text=fetch.get_page_text) -> list[dict]:
    """Fetch every source page once and keep its text, so the answers are checked
    against exactly the text that was read."""
    folder.mkdir(parents=True, exist_ok=True)
    index = []
    for card in sources["cards"]:
        for i, url in enumerate(card["urls"]):
            page = get_text(url)
            name = _page_file(card["id"], i)
            (folder / name).write_text(page.text, encoding="utf-8")
            index.append({"card": card["id"], "url": url, "file": name, "method": page.method,
                          "chars": len(page.text), "note": page.note})
    (folder / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index


def saved_page_reader(folder: Path = PAGES_DIR):
    """A `get_text` that returns the saved text instead of downloading again."""
    index = {row["url"]: row for row in json.loads((folder / "index.json").read_text(encoding="utf-8"))}

    def get_text(url: str) -> fetch.PageText:
        row = index.get(url)
        if row is None:
            return fetch.PageText(url, "", "none", "this page was not saved; run save-pages again")
        text = (folder / row["file"]).read_text(encoding="utf-8")
        return fetch.PageText(url, text, row["method"] if text else "none", row.get("note") or "")
    return get_text


class FileExtractor:
    """Same `extract` method as ClaudeExtractor, answered from out/answers/."""

    def __init__(self, folder: Path = ANSWERS_DIR) -> None:
        self.answers: dict[str, dict] = {}
        for path in sorted(folder.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.answers[data["card"]] = data.get("pages", {})

    def extract(self, card: dict, url: str, page_text: str, existing: list[dict]) -> list[dict]:
        pages = self.answers.get(card["id"])
        if pages is None or url not in pages:
            raise ExtractionError("no answer file entry for this page (it was not read)")
        benefits = pages[url]
        if not isinstance(benefits, list):
            raise ExtractionError("the answer for this page is not a list")
        return benefits


def _starts_from_uncommitted_catalog() -> bool:
    from . import publish
    return publish.catalog_changed()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Card Credits catalog update without the API")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("save-pages", help="fetch every source page into out/pages/")
    run_cmd = sub.add_parser("run", help="build catalog.json from out/answers/")
    run_cmd.add_argument("--today", default=datetime.date.today().isoformat())
    run_cmd.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    sources = load_json(config.SOURCES_PATH)

    if args.command == "save-pages":
        for row in save_pages(sources):
            print(f"{row['card']:28} {row['method']:14} {row['chars']:>7}  {row['note'] or ''}")
        return 0

    if args.publish and _starts_from_uncommitted_catalog():
        print("ERROR: catalog.json already differs from the committed copy. A run must start from "
              "main's catalog, or big changes would be compared with themselves and published "
              "without review. Run `git checkout -- catalog.json` and try again.")
        return 1
    catalog = load_json(config.CATALOG_PATH)
    if catalog_errors(catalog):
        print("ERROR: catalog.json is already invalid; fix it before updating.")
        return 1
    result = run(catalog, sources, args.today, saved_page_reader(), FileExtractor())
    summary = (
        "_This check ran without the Claude API: Claude Code read the saved issuer pages on the "
        "owner's own plan, and every benefit passed the same word-for-word quote check as the "
        "automatic job._\n\n" + report.summary_markdown(result.changes, args.today))
    print(summary)
    if catalog_errors(result.catalog):
        print("ERROR: refusing to write a catalog that fails validation.")
        return 1
    config.CATALOG_PATH.write_text(dump_catalog(result.catalog), encoding="utf-8")
    config.OUT_DIR.mkdir(exist_ok=True)
    (config.OUT_DIR / "summary.md").write_text(summary, encoding="utf-8")
    print(f"catalog.json written. Needs review: {'yes' if result.big else 'no'}.")
    if args.publish:
        from . import publish
        return publish.publish(result.big, report.title(result.changes, args.today), summary, args.today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
