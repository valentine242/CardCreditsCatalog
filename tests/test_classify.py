import copy

import pytest

from job.classify import BIG, SAFE, classify, has_big
from tests.helpers import benefit, catalog


def diff(old_benefit, new_benefit):
    return classify(catalog(old_benefit), catalog(new_benefit))


SAFE_CASES = {
    "name reworded": dict(name="Dining Statement Credit"),
    "setup step changed": dict(setup_step="Enroll in your account"),
    "setup step removed": dict(setup_step=None),
    "details changed": dict(details="At partner restaurants in the U.S."),
    "last_verified refreshed": dict(last_verified="2026-11-16"),
    "source link changed": dict(source_url="https://www.americanexpress.com/new"),
}


@pytest.mark.parametrize("label", SAFE_CASES)
def test_safe_changes(label):
    changes = diff(benefit(), benefit(**SAFE_CASES[label]))
    assert changes and all(c.severity == SAFE for c in changes), label
    assert not has_big(changes)


def test_first_confirmation_is_safe():
    old = benefit(status="needs_review", source_url=None, last_verified=None)
    changes = diff(old, benefit())
    assert changes and not has_big(changes)


BIG_CASES = {
    "value_usd changed": dict(value_usd=15.0),
    "value_text changed": dict(value_text="$10.00 per month"),
    "amount no longer stated": dict(value_usd=None, value_text=""),
    "period changed": dict(period="Quarterly"),
    "category changed": dict(category="Food delivery"),
    "end_date added": dict(end_date="2026-12-31"),
    "benefit removed": dict(status="removed"),
}


@pytest.mark.parametrize("label", BIG_CASES)
def test_big_changes(label):
    changes = diff(benefit(), benefit(**BIG_CASES[label]))
    assert has_big(changes), label


def test_end_date_changed_or_dropped_is_big():
    dated = benefit(period="One time", end_date="2026-12-31")
    assert has_big(diff(dated, benefit(period="One time", end_date="2027-01-31")))
    assert has_big(diff(dated, benefit(period="One time", end_date=None)))
    assert has_big(diff(dated, benefit(period="One time")))


def test_perk_wording_change_is_big():
    night = benefit(value_usd=None, value_text="1 night")
    assert has_big(diff(night, benefit(value_usd=None, value_text="2 nights")))


def test_benefit_added_is_big():
    changes = classify(catalog(benefit()), catalog(benefit(), benefit(id="new-credit", name="New")))
    assert [c.kind for c in changes if c.severity == BIG] == ["benefit added"]


def test_benefit_coming_back_is_big():
    assert has_big(diff(benefit(status="removed"), benefit()))


def test_benefit_deleted_outright_is_big():
    assert has_big(classify(catalog(benefit(), benefit(id="b")), catalog(benefit())))


def test_new_card_is_big():
    old = catalog(benefit())
    new = copy.deepcopy(old)
    new["cards"].append({"id": "new-card", "name": "New Card", "issuer": "Chase",
                         "benefits": [benefit()]})
    kinds = [c.kind for c in classify(old, new) if c.severity == BIG]
    assert kinds == ["new card", "benefit added"]


def test_card_deleted_is_big():
    old = catalog(benefit())
    new = copy.deepcopy(old)
    old["cards"].append({"id": "gone", "name": "Gone", "issuer": "Chase", "benefits": []})
    assert has_big(classify(old, new))


def test_no_change_is_no_change():
    assert classify(catalog(benefit()), catalog(benefit())) == []
    dated = catalog(benefit())
    dated["generated"] = "2026-11-16"
    assert classify(catalog(benefit()), dated) == []


def test_same_amount_as_whole_number_is_not_a_change():
    assert diff(benefit(value_usd=10.0), benefit(value_usd=10)) == []


def test_safe_and_big_together_keep_both():
    changes = diff(benefit(), benefit(value_usd=15.0, value_text="$15.00", details="New words."))
    assert {c.severity for c in changes} == {SAFE, BIG}


def test_rows_carry_what_the_summary_needs():
    change = next(c for c in diff(benefit(), benefit(value_usd=15.0)) if c.severity == BIG)
    assert change.card == "Test Card" and change.benefit == "Dining Credit"
    assert "$10.00" in change.old and "$15.00" in change.new
    assert change.source_url.startswith("https://")
