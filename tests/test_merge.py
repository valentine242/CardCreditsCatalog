import copy

from job.merge import merge_card, merge_catalog, mint_id, normalise_name, slugify
from job.validate import catalog_errors
from tests.helpers import TODAY, URL, benefit, catalog, seed


def found(**over):
    base = {"existing_id": None, "name": "Dining Credit", "category": "Dining",
            "value_text": "$10.00", "value_usd": 10.0, "period": "Monthly",
            "setup_step": "Enroll first", "details": "At partner restaurants.",
            "end_date": None, "source_url": URL}
    base.update(over)
    return base


def card_with(*benefits):
    return catalog(*benefits)["cards"][0]


# ------------------------------------------------------------- stable ids

def test_match_by_id_keeps_id_when_the_name_changes():
    card = card_with(benefit(id="dining-credit"))
    out = merge_card(card, [found(existing_id="dining-credit", name="Resy Dining Credit")],
                     TODAY, complete=True)
    assert [b["id"] for b in out["benefits"]] == ["dining-credit"]
    assert out["benefits"][0]["name"] == "Resy Dining Credit"


def test_match_by_normalised_name_keeps_id():
    card = card_with(benefit(id="some-old-id", name="Dining Credit"))
    out = merge_card(card, [found(name="DINING  Credit®")], TODAY, complete=True)
    assert [b["id"] for b in out["benefits"]] == ["some-old-id"]


def test_id_wins_over_name():
    card = card_with(benefit(id="a", name="Dining Credit"), benefit(id="b", name="Other"))
    out = merge_card(card, [found(existing_id="b", name="Dining Credit")], TODAY, complete=False)
    by_id = {b["id"]: b for b in out["benefits"]}
    assert by_id["b"]["last_verified"] == TODAY and by_id["a"]["last_verified"] != TODAY


def test_unknown_existing_id_falls_back_to_name_then_new_slug():
    card = card_with(benefit(id="dining-credit"))
    out = merge_card(card, [found(existing_id="made-up"),
                            found(existing_id="made-up", name="Uber Cash")],
                     TODAY, complete=True)
    assert [b["id"] for b in out["benefits"]] == ["dining-credit", "uber-cash"]


def test_new_benefit_gets_a_slug_and_never_reuses_an_id():
    card = card_with(benefit(id="hotel-credit", name="Old hotel thing", status="removed"))
    out = merge_card(card, [found(name="Hotel Credit")], TODAY, complete=True)
    assert [b["id"] for b in out["benefits"]] == ["hotel-credit", "hotel-credit-2"]
    assert out["benefits"][0]["status"] == "removed"


def test_ids_and_order_never_change_across_runs():
    card = card_with(benefit(id="a", name="A"), benefit(id="b", name="B"), benefit(id="c", name="C"))
    first = merge_card(card, [found(name="C"), found(name="New One"), found(name="A")],
                       TODAY, complete=True)
    second = merge_card(first, [found(name="New One"), found(name="A"), found(name="C")],
                        "2026-11-23", complete=True)
    assert [b["id"] for b in first["benefits"]] == ["a", "b", "c", "new-one"]
    assert [b["id"] for b in second["benefits"]] == ["a", "b", "c", "new-one"]


def test_two_page_benefits_cannot_claim_one_catalog_entry():
    card = card_with(benefit())
    out = merge_card(card, [found(), found()], TODAY, complete=True)
    assert [b["id"] for b in out["benefits"]] == ["dining-credit", "dining-credit-2"]


def test_slug_helpers():
    assert slugify("10,000-mile award flight discount") == "10-000-mile-award-flight-discount"
    assert slugify("CLEAR® Plus Credit") == "clear-plus-credit"
    assert slugify("®") == "benefit"
    assert normalise_name(" Uber  Cash™ ") == "uber cash"
    assert mint_id("Uber Cash", {"uber-cash", "uber-cash-2"}) == "uber-cash-3"


# ---------------------------------------------------------- merge behaviour

def test_confirmed_benefit_is_verified_today_with_its_source():
    card = card_with(benefit(status="needs_review", source_url=None, last_verified=None))
    out = merge_card(card, [found()], TODAY, complete=True)["benefits"][0]
    assert (out["status"], out["last_verified"], out["source_url"]) == ("verified", TODAY, URL)


def test_missing_benefit_is_kept_as_removed_not_deleted():
    gone = benefit(id="old-credit", name="Old Credit")
    out = merge_card(card_with(benefit(), gone), [found()], TODAY, complete=True)
    old = next(b for b in out["benefits"] if b["id"] == "old-credit")
    assert len(out["benefits"]) == 2
    assert old["status"] == "removed"
    # everything else about it is kept for people's history
    assert {k: v for k, v in old.items() if k != "status"} == \
           {k: v for k, v in gone.items() if k != "status"}


def test_nothing_is_removed_when_the_card_was_not_fully_read():
    out = merge_card(card_with(benefit(), benefit(id="old-credit", name="Old Credit")),
                     [found()], TODAY, complete=False)
    assert [b["status"] for b in out["benefits"]] == ["verified", "verified"]
    assert out["benefits"][1]["last_verified"] != TODAY


def test_removed_benefit_comes_back_under_the_same_id():
    out = merge_card(card_with(benefit(status="removed")), [found()], TODAY, complete=True)
    assert out["benefits"][0]["id"] == "dining-credit"
    assert out["benefits"][0]["status"] == "verified"


def test_page_values_replace_catalog_values():
    out = merge_card(card_with(benefit()), [found(value_usd=15.0, value_text="$15.00",
                                                  period="Quarterly", setup_step=None)],
                     TODAY, complete=True)["benefits"][0]
    assert (out["value_usd"], out["value_text"], out["period"], out["setup_step"]) == \
           (15.0, "$15.00", "Quarterly", None)


def test_end_date_only_appears_when_stated():
    out = merge_card(card_with(benefit()), [found()], TODAY, complete=True)["benefits"][0]
    assert "end_date" not in out
    dated = merge_card(card_with(benefit(period="One time")),
                       [found(period="One time", end_date="2026-12-31")],
                       TODAY, complete=True)["benefits"][0]
    assert dated["end_date"] == "2026-12-31"
    cleared = merge_card(card_with(dated), [found(period="One time")],
                         TODAY, complete=True)["benefits"][0]
    assert cleared["end_date"] is None


def test_input_is_not_modified():
    card = card_with(benefit())
    before = copy.deepcopy(card)
    merge_card(card, [found(name="Other")], TODAY, complete=True)
    assert card == before


def test_catalog_merge_adds_new_cards_last_and_leaves_others_alone():
    old = seed()
    new_card = {"id": "test-brand-new-card", "name": "Brand New Card",
                "issuer": "Capital One"}           # an id the live catalog never has
    new = merge_catalog(old, [{"card": new_card, "found": [found(name="Travel Credit")],
                               "complete": True}], TODAY)
    assert [c["id"] for c in new["cards"]] == [c["id"] for c in old["cards"]] + [new_card["id"]]
    assert new["cards"][:len(old["cards"])] == old["cards"]
    assert new["generated"] == TODAY
    assert catalog_errors(new) == []


def test_card_with_nothing_found_is_untouched_and_new_card_not_added():
    old = catalog(benefit())
    results = [
        {"card": {"id": "test-card", "name": "Test Card", "issuer": "x"}, "found": [], "complete": False},
        {"card": {"id": "brand-new", "name": "Brand New", "issuer": "x"}, "found": [], "complete": False},
    ]
    assert merge_catalog(old, results, TODAY)["cards"] == old["cards"]
