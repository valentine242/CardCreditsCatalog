"""Decide which changes are safe to publish on their own and which need the
owner's eyes.

Safe: wording (name), setup step or details changed, the source link changed,
      last_verified refreshed, or a benefit went from needs_review to verified
      with nothing else different.
Big:  any amount changed (value_usd or value_text), a benefit added or
      removed (or brought back), a new card, a card missing, a period, category
      or end_date changed, plus run problems (a page that yielded nothing, a
      validation failure), which update.py adds.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

SAFE = "safe"
BIG = "big"

BIG_FIELDS = {
    "value_usd": "amount changed",
    "value_text": "amount changed",
    "period": "period changed",
    "category": "category changed",
    "end_date": "end date changed",
}
SAFE_FIELDS = {
    "name": "name reworded",
    "setup_step": "setup step changed",
    "details": "details changed",
    "source_url": "source link changed",
    "last_verified": "checked again",
}


@dataclass
class Change:
    severity: str          # SAFE or BIG
    kind: str              # short plain-English label
    card: str              # card name
    benefit: str = ""      # benefit name ("" for card-level changes)
    old: str = ""
    new: str = ""
    source_url: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _show(value) -> str:
    if value is None:
        return "(none)"
    if isinstance(value, float):
        return f"${value:,.2f}"
    return str(value)


def _same(field: str, a, b) -> bool:
    if field == "value_usd" and a is not None and b is not None:
        return abs(float(a) - float(b)) < 0.005
    return a == b


def _amount(benefit: dict) -> str:
    return f"{benefit.get('value_text') or '(no amount)'} · {benefit.get('period')}"


def classify_benefit(card_name: str, old: dict, new: dict) -> list[Change]:
    link = new.get("source_url") or old.get("source_url") or ""
    name = new.get("name") or old.get("name") or ""
    changes: list[Change] = []

    was, now = old.get("status"), new.get("status")
    if was != now:
        if now == "removed":
            return [Change(BIG, "benefit removed", card_name, name,
                           _amount(old), "no longer on the issuer's page", link)]
        if was == "removed":
            changes.append(Change(BIG, "benefit is back", card_name, name,
                                  "removed", _amount(new), link))
        elif (was, now) == ("needs_review", "verified"):
            changes.append(Change(SAFE, "confirmed by the page", card_name, name,
                                  "needs review", "verified", link))
        else:
            changes.append(Change(BIG, "status changed", card_name, name,
                                  _show(was), _show(now), link))

    for field, label in BIG_FIELDS.items():
        if not _same(field, old.get(field), new.get(field)):
            changes.append(Change(BIG, label, card_name, name,
                                  f"{field}: {_show(old.get(field))}",
                                  f"{field}: {_show(new.get(field))}", link))
    for field, label in SAFE_FIELDS.items():
        if old.get(field) != new.get(field):
            changes.append(Change(SAFE, label, card_name, name,
                                  _show(old.get(field)), _show(new.get(field)), link))
    return changes


def classify(old_catalog: dict, new_catalog: dict) -> list[Change]:
    """Every difference between two catalogs, each marked safe or big."""
    changes: list[Change] = []
    old_cards = {c["id"]: c for c in old_catalog.get("cards", [])}
    new_cards = {c["id"]: c for c in new_catalog.get("cards", [])}

    for card_id, new_card in new_cards.items():
        old_card = old_cards.get(card_id)
        if old_card is None:
            changes.append(Change(BIG, "new card", new_card["name"], "", "",
                                  f"{len(new_card['benefits'])} benefits"))
            for b in new_card["benefits"]:
                changes.append(Change(BIG, "benefit added", new_card["name"], b["name"],
                                      "", _amount(b), b.get("source_url") or ""))
            continue
        for field in ("name", "issuer"):
            if old_card.get(field) != new_card.get(field):
                changes.append(Change(SAFE, f"card {field} reworded", new_card["name"], "",
                                      _show(old_card.get(field)), _show(new_card.get(field))))
        old_benefits = {b["id"]: b for b in old_card["benefits"]}
        new_benefits = {b["id"]: b for b in new_card["benefits"]}
        for benefit_id, b in new_benefits.items():
            if benefit_id not in old_benefits:
                changes.append(Change(BIG, "benefit added", new_card["name"], b["name"],
                                      "", _amount(b), b.get("source_url") or ""))
            else:
                changes.extend(classify_benefit(new_card["name"], old_benefits[benefit_id], b))
        for benefit_id, b in old_benefits.items():
            if benefit_id not in new_benefits:
                changes.append(Change(BIG, "benefit deleted from the file", new_card["name"],
                                      b["name"], _amount(b), "(gone)", b.get("source_url") or ""))

    for card_id, old_card in old_cards.items():
        if card_id not in new_cards:
            changes.append(Change(BIG, "card deleted from the file", old_card["name"], "",
                                  f"{len(old_card['benefits'])} benefits", "(gone)"))
    return changes


def has_big(changes: list[Change]) -> bool:
    return any(c.severity == BIG for c in changes)
