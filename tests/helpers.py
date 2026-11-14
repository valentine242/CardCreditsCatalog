"""Shared test pieces: a fake Claude, fake pages, small catalogs. No network."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from job.fetch import PageText

ROOT = Path(__file__).resolve().parent.parent
TODAY = "2026-11-16"
URL = "https://www.americanexpress.com/us/credit-cards/card/test-card/"

PAGE = """\
Test Card benefits
$120 Dining Credit: earn up to $10 in statement credits monthly at partner restaurants. Enrollment required.
$200 Hotel Credit: get $200 back in statement credits each calendar year on prepaid bookings.
Free Night Award: receive 1 Free Night Award every year after your Card renewal month.
Lounge access and travel insurance are also included with this credit card.
"""


def seed() -> dict:
    return json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))


def benefit(**over) -> dict:
    base = {
        "id": "dining-credit", "name": "Dining Credit", "category": "Dining",
        "value_text": "$10.00", "value_usd": 10.0, "period": "Monthly",
        "setup_step": "Enroll first", "details": "At partner restaurants.",
        "source_url": URL, "last_verified": "2026-11-09", "status": "verified",
    }
    base.update(over)
    return base


def catalog(*benefits: dict, card_id: str = "test-card") -> dict:
    return {
        "schema_version": 1, "generated": "2026-11-09",
        "cards": [{"id": card_id, "name": "Test Card", "issuer": "American Express",
                   "benefits": [copy.deepcopy(b) for b in benefits]}],
    }


def sources(card_id: str = "test-card", urls: tuple[str, ...] = (URL,)) -> dict:
    return {"cards": [{"id": card_id, "name": "Test Card",
                       "issuer": "American Express", "urls": list(urls)}]}


def claim(**over) -> dict:
    """One benefit as Claude would return it."""
    base = {
        "existing_id": None, "name": "Dining Credit", "category": "Dining",
        "value_usd": 10, "value_text": "$10", "period": "Monthly",
        "setup_step": "Enroll first", "details": "At partner restaurants.",
        "end_date": None,
        "evidence": "earn up to $10 in statement credits monthly at partner restaurants",
    }
    base.update(over)
    return base


HOTEL = dict(name="Hotel Credit", category="Hotels", value_usd=200, value_text="$200",
             period="Annual", setup_step=None, details="Prepaid bookings.",
             evidence="get $200 back in statement credits each calendar year")
NIGHT = dict(name="Free Night Award", category="Hotels", value_usd=None,
             value_text="1 night", period="Anniversary", setup_step=None, details=None,
             evidence="receive 1 Free Night Award every year after your Card renewal month")


class FakeClaude:
    """Stands in for ClaudeExtractor: returns canned answers per URL and
    remembers what it was asked."""

    def __init__(self, answers: dict[str, object]):
        self.answers = answers
        self.calls: list[dict] = []

    def extract(self, card, url, page_text, existing):
        self.calls.append({"card": card, "url": url, "page_text": page_text,
                           "existing": existing})
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)


def pages(mapping: dict[str, str | None]):
    """A get_text function: text for each URL, or None for a page that fails."""
    def get_text(url: str) -> PageText:
        text = mapping[url]
        if text is None:
            return PageText(url, "", "none", "no benefit text")
        return PageText(url, text, "plain")
    return get_text
