"""Fold what the pages state into the catalog, keeping every id stable.

Nothing is ever deleted: a benefit that left its page stays with status
"removed" so the app can keep people's history for it.
"""
from __future__ import annotations

import copy
import re

BENEFIT_KEYS = [
    "id", "name", "category", "value_text", "value_usd", "period", "setup_step",
    "details", "source_url", "last_verified", "status",
]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "benefit"


def normalise_name(text: str) -> str:
    """Names compare equal when only case, punctuation or ® ™ marks differ."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def mint_id(name: str, taken: set[str]) -> str:
    """A new slug id that no benefit on this card has ever used."""
    base = slugify(name)
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _find_existing(found: dict, benefits: list[dict], claimed: set[str]) -> dict | None:
    """Match by id first, then by normalised name."""
    wanted = found.get("existing_id")
    if wanted:
        for b in benefits:
            if b["id"] == wanted and b["id"] not in claimed:
                return b
    key = normalise_name(found["name"])
    for b in benefits:
        if normalise_name(b["name"]) == key and b["id"] not in claimed:
            return b
    return None


def merge_card(
    card: dict,
    found: list[dict],
    today: str,
    *,
    complete: bool,
) -> dict:
    """Return a new copy of `card` with the page's benefits merged in.

    found       benefits the page(s) state (from extract.ground)
    complete    True only when every page of this card was read and every
                claim about it was backed by the page; only then may a benefit
                that is missing be marked "removed"
    """
    card = copy.deepcopy(card)
    benefits: list[dict] = card["benefits"]
    claimed: set[str] = set()
    taken = {b["id"] for b in benefits}

    for item in found:
        existing = _find_existing(item, benefits, claimed)
        if existing is None:
            new_id = mint_id(item["name"], taken)
            taken.add(new_id)
            existing = {"id": new_id}
            benefits.append(existing)
        claimed.add(existing["id"])

        same_perk_wording = (
            item["value_usd"] is None
            and existing.get("value_usd") is None
            and normalise_name(item["value_text"]) == normalise_name(existing.get("value_text") or "")
        )
        updated = {
            "id": existing["id"],
            "name": item["name"],
            "category": item["category"],
            "value_text": existing.get("value_text", "") if same_perk_wording else item["value_text"],
            "value_usd": item["value_usd"],
            "period": item["period"],
            "setup_step": item["setup_step"],
            "details": item["details"],
            "source_url": item["source_url"],
            "last_verified": today,
            "status": "verified",
        }
        if item.get("end_date") or "end_date" in existing:
            updated["end_date"] = item.get("end_date")
        existing.clear()
        existing.update(updated)

    if complete:
        for b in benefits:
            if b["id"] not in claimed and b["status"] != "removed":
                b["status"] = "removed"
    return card


def merge_catalog(catalog: dict, results: list[dict], today: str, note: str | None = None) -> dict:
    """`results`: one per card read this run:
    {"card": {id, name, issuer}, "found": [...], "complete": bool}
    A card with nothing found is left exactly as it was (and a new card is not added)."""
    new = copy.deepcopy(catalog)
    by_id = {c["id"]: c for c in new["cards"]}
    for result in results:
        if not result["found"]:
            continue
        source = result["card"]
        card = by_id.get(source["id"])
        if card is None:
            card = {"id": source["id"], "name": source["name"],
                    "issuer": source["issuer"], "benefits": []}
            new["cards"].append(card)
            by_id[card["id"]] = card
        merged = merge_card(card, result["found"], today, complete=result["complete"])
        card.clear()
        card.update(merged)
    new["generated"] = today
    if note is not None:
        new["note"] = note
    return new
