"""A card's two display hints: `short_name` and `color`. They say how the app names and colours a
card in a list. They live in sources.json (curated by the owner) and are copied into the catalog
as they are; a change to either is a safe change."""
import copy
import json

import pytest

from job import config
from job.classify import SAFE, classify, has_big
from job.merge import DISPLAY_FIELDS, apply_display_hints, merge_catalog, with_display_hints
from job.update import run
from job.validate import catalog_errors, load_schema, sources_errors
from tests.helpers import (PAGE, TODAY, URL, FakeClaude, benefit, catalog, claim, pages, seed,
                           sources)

COLOURS = ["gold", "platinum", "silver", "black", "blue", "green", "red", "purple", "white", "rose"]


def hinted(short_name="Test", color="gold", **over) -> dict:
    """sources.json for the test card, with display hints."""
    src = sources(**over)
    if short_name is not None:
        src["cards"][0]["short_name"] = short_name
    if color is not None:
        src["cards"][0]["color"] = color
    return src


def with_hints(cat: dict, **hints) -> dict:
    cat = copy.deepcopy(cat)
    cat["cards"][0].update(hints)
    return cat


# ------------------------------------------------------------------ schema

def test_schema_accepts_the_two_fields_and_every_colour_family():
    assert load_schema()["$defs"]["card"]["properties"]["color"]["enum"] == COLOURS
    for colour in COLOURS:
        assert catalog_errors(with_hints(catalog(benefit()), short_name="Platinum", color=colour)) == []
    # Each one alone is fine too.
    assert catalog_errors(with_hints(catalog(benefit()), short_name="Bonvoy Brilliant")) == []
    assert catalog_errors(with_hints(catalog(benefit()), color="black")) == []
    assert catalog_errors(with_hints(catalog(benefit()), short_name="x" * 24)) == []


@pytest.mark.parametrize("hints", [
    dict(color="orange"),            # not one of the families
    dict(color="Gold"),              # families are lower case
    dict(color="#c9a46a"),           # a family, never an exact colour
    dict(color=None),                # left out, not null
    dict(short_name=""),
    dict(short_name="x" * 25),
    dict(short_name=7),
    dict(nickname="Plat"),           # still no other new fields
])
def test_schema_rejects(hints):
    assert catalog_errors(with_hints(catalog(benefit()), **hints)) != []


def test_old_catalogs_still_validate():
    # The published catalog and a card with neither field: both optional.
    old = seed()
    assert catalog_errors(old) == []
    for card in old["cards"]:
        for field in DISPLAY_FIELDS:
            card.pop(field, None)
    assert catalog_errors(old) == []
    assert catalog_errors(catalog(benefit())) == []
    assert "short_name" not in load_schema()["$defs"]["card"]["required"]
    assert "color" not in load_schema()["$defs"]["card"]["required"]


# ------------------------------------------------------------------ sources.json

def test_sources_file_has_valid_hints_for_all_15_cards():
    src = json.loads(config.SOURCES_PATH.read_text(encoding="utf-8"))
    assert sources_errors(src) == []
    names = [c.get("short_name") for c in src["cards"]]
    assert all(names) and len(set(names)) == 15, "every card has its own short name"
    for card in src["cards"]:
        assert len(card["short_name"]) <= 24
        # From the card's own official name: every word of the short name is in the name or the issuer.
        official = (card["name"] + " " + card["issuer"]).lower()
        assert all(word in official for word in card["short_name"].lower().split()), card["id"]
        assert card.get("color") is None or card["color"] in COLOURS


def test_a_mistake_in_sources_is_caught_before_a_run():
    assert sources_errors(hinted(color="orange")) != []
    assert sources_errors(hinted(short_name="")) != []
    assert sources_errors(hinted(short_name="A name far too long for a list row")) != []
    assert sources_errors(hinted()) == []
    assert sources_errors(sources()) == []                      # no hints at all is fine
    assert "test-card" in sources_errors(hinted(color="orange"))[0]


# ------------------------------------------------------------------ merge

def test_hints_pass_through_merge_unchanged():
    src = hinted(short_name="Bonvoy Brilliant", color="black")["cards"][0]
    found = [dict(claim(), source_url=URL, existing_id="dining-credit")]
    new = merge_catalog(catalog(benefit()), [{"card": src, "found": found, "complete": True}], TODAY)
    card = new["cards"][0]
    assert card["short_name"] == "Bonvoy Brilliant" and card["color"] == "black"
    assert list(card) == ["id", "name", "issuer", "short_name", "color", "benefits"]
    assert catalog_errors(new) == []
    # A new card gets them as well.
    brand_new = dict(src, id="brand-new")
    added = merge_catalog(catalog(benefit()), [{"card": brand_new, "found": found, "complete": True}], TODAY)
    assert added["cards"][1]["short_name"] == "Bonvoy Brilliant" and added["cards"][1]["color"] == "black"


def test_only_the_hints_given_are_copied_and_a_dropped_hint_leaves_the_card():
    card = catalog(benefit())["cards"][0]
    assert with_display_hints(card, {"short_name": "Test"}) == {**card, "short_name": "Test"}
    assert "color" not in with_display_hints(card, {"short_name": "Test"})
    # sources.json is where the hints live: one taken out there leaves the catalog too.
    had = dict(card, short_name="Old", color="gold")
    assert with_display_hints(had, {}) == card
    assert with_display_hints(had, {"color": "blue"})["color"] == "blue"
    # Nothing else on the card is touched, and the input is not modified.
    assert with_display_hints(had, {"color": "blue"})["benefits"] == card["benefits"]
    assert had["color"] == "gold"


def test_every_listed_card_gets_its_hints_even_when_its_page_gave_nothing():
    old = catalog(benefit())
    result = run(old, hinted(), TODAY, pages({URL: None}), FakeClaude({}))
    card = result.catalog["cards"][0]
    assert card["short_name"] == "Test" and card["color"] == "gold"
    assert card["benefits"] == old["cards"][0]["benefits"]         # nothing else changed
    assert catalog_errors(result.catalog) == []
    # A card the catalog doesn't have is not added just because sources.json has hints for it.
    other = apply_display_hints(old, hinted(card_id="not-in-the-catalog"))
    assert other["cards"] == old["cards"]


def test_a_full_run_carries_the_hints_and_calls_them_safe():
    old = catalog(benefit(last_verified=TODAY))
    result = run(old, hinted(short_name="Test", color="rose"), TODAY, pages({URL: PAGE}),
                 FakeClaude({URL: [claim(existing_id="dining-credit")]}))
    card = result.catalog["cards"][0]
    assert (card["short_name"], card["color"]) == ("Test", "rose")
    kinds = {c.kind: c for c in result.changes}
    assert kinds["card short name changed"].severity == SAFE
    assert kinds["card colour changed"].severity == SAFE
    assert (kinds["card colour changed"].old, kinds["card colour changed"].new) == ("(none)", "rose")
    assert not result.big
    # A second run with the same sources changes nothing about the hints.
    again = run(result.catalog, hinted(short_name="Test", color="rose"), TODAY, pages({URL: PAGE}),
                FakeClaude({URL: [claim(existing_id="dining-credit")]}))
    assert not [c for c in again.changes if c.kind.startswith("card ")]


# ------------------------------------------------------------------ classify

@pytest.mark.parametrize("old_hints, new_hints, kind", [
    (dict(), dict(short_name="Platinum"), "card short name changed"),            # added
    (dict(short_name="Plat"), dict(short_name="Platinum"), "card short name changed"),
    (dict(short_name="Platinum"), dict(), "card short name changed"),            # taken away
    (dict(), dict(color="platinum"), "card colour changed"),
    (dict(color="silver"), dict(color="platinum"), "card colour changed"),
    (dict(color="platinum"), dict(), "card colour changed"),
])
def test_changing_a_hint_is_safe(old_hints, new_hints, kind):
    changes = classify(with_hints(catalog(benefit()), **old_hints), with_hints(catalog(benefit()), **new_hints))
    assert [c.kind for c in changes] == [kind]
    assert changes[0].severity == SAFE and not has_big(changes)
    assert changes[0].card == "Test Card" and changes[0].benefit == ""


def test_hints_do_not_hide_a_big_change():
    old = catalog(benefit())
    new = with_hints(catalog(benefit(value_usd=15.0, value_text="$15.00")), color="gold")
    changes = classify(old, new)
    assert has_big(changes) and any(c.kind == "card colour changed" for c in changes)
    assert classify(with_hints(old, color="gold"), with_hints(old, color="gold")) == []
