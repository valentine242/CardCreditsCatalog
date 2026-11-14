"""Check a catalog against schema/catalog.schema.json plus the rules a JSON
Schema can't express (unique ids).

    python -m job.validate catalog.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from . import config


def load_schema() -> dict:
    return json.loads(config.SCHEMA_PATH.read_text(encoding="utf-8"))


def catalog_errors(catalog: object) -> list[str]:
    """Every problem found, in plain words. Empty list = valid."""
    errors: list[str] = []
    validator = Draft202012Validator(load_schema())
    for err in sorted(validator.iter_errors(catalog), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(top level)"
        errors.append(f"{where}: {err.message}")
    if errors or not isinstance(catalog, dict):
        return errors

    seen_cards: set[str] = set()
    for card in catalog["cards"]:
        if card["id"] in seen_cards:
            errors.append(f"card id '{card['id']}' is used twice")
        seen_cards.add(card["id"])
        seen_benefits: set[str] = set()
        for benefit in card["benefits"]:
            if benefit["id"] in seen_benefits:
                errors.append(f"{card['id']}: benefit id '{benefit['id']}' is used twice")
            seen_benefits.add(benefit["id"])
    return errors


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else config.CATALOG_PATH
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {path} can't be read as JSON: {exc}")
        return 1
    errors = catalog_errors(catalog)
    if errors:
        print(f"INVALID: {path} has {len(errors)} problem(s):")
        for line in errors:
            print(f"  - {line}")
        return 1
    cards = catalog["cards"]
    print(f"OK: {path.name} is valid ({len(cards)} cards, "
          f"{sum(len(c['benefits']) for c in cards)} benefits).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
