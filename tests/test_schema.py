import copy
import json

import pytest

from job.validate import catalog_errors, main
from tests.helpers import ROOT, benefit, catalog, seed


def test_published_catalog_passes():
    assert catalog_errors(seed()) == []


def test_seed_cards_pass_with_their_ids():
    ids = [c["id"] for c in seed()["cards"]][:9]
    assert ids == [
        "chase-sapphire-reserve", "chase-united-club", "amex-platinum", "amex-gold",
        "amex-blue-cash-preferred", "amex-delta-reserve", "amex-marriott-brilliant",
        "chase-united-quest", "amex-hilton-aspire",
    ]


def test_good_catalog_passes():
    good = catalog(
        benefit(),
        benefit(id="free-night", name="Free Night", value_text="1 night", value_usd=None,
                period="Anniversary", category="Hotels"),
        benefit(id="promo", period="One time", end_date="2026-12-31"),
        benefit(id="old", status="removed"),
        benefit(id="unchecked", status="needs_review", source_url=None, last_verified=None),
    )
    good["note"] = "A note."
    assert catalog_errors(good) == []


BAD_BENEFITS = {
    "category Other": dict(category="Other"),
    "unknown period": dict(period="Weekly"),
    "unknown status": dict(status="pending"),
    "id not a slug": dict(id="Dining Credit"),
    "amount as text": dict(value_usd="10"),
    "negative amount": dict(value_usd=-5),
    "zero amount": dict(value_usd=0),
    "value_text missing": dict(value_text=None),
    "empty name": dict(name=""),
    "bad date": dict(last_verified="16/11/2026"),
    "impossible month": dict(last_verified="2026-13-01"),
    "bad end date": dict(period="One time", end_date="soon"),
    "end date on a repeating benefit": dict(period="Monthly", end_date="2026-12-31"),
    "verified without a source": dict(status="verified", source_url=None),
    "verified without a date": dict(status="verified", last_verified=None),
    "source not https": dict(source_url="http://example.com"),
    "unknown field": dict(points_multiplier=3),
}


@pytest.mark.parametrize("label", BAD_BENEFITS)
def test_bad_benefit_fails(label):
    assert catalog_errors(catalog(benefit(**BAD_BENEFITS[label]))) != [], label


@pytest.mark.parametrize("field", ["id", "name", "category", "value_text", "value_usd",
                                   "period", "setup_step", "details", "source_url",
                                   "last_verified", "status"])
def test_missing_benefit_field_fails(field):
    broken = benefit()
    del broken[field]
    assert catalog_errors(catalog(broken)) != []


def test_bad_top_level_fails():
    for change in (dict(schema_version=2), dict(generated="yesterday"), dict(cards=[]),
                   dict(cards="none"), dict(extra=True)):
        bad = catalog(benefit())
        bad.update(change)
        assert catalog_errors(bad) != [], change
    for missing in ("schema_version", "generated", "cards"):
        bad = catalog(benefit())
        del bad[missing]
        assert catalog_errors(bad) != [], missing
    assert catalog_errors([]) != []


def test_duplicate_ids_fail():
    assert any("used twice" in e for e in catalog_errors(catalog(benefit(), benefit())))
    twice = catalog(benefit())
    twice["cards"].append(copy.deepcopy(twice["cards"][0]))
    assert any("card id" in e for e in catalog_errors(twice))


def test_same_benefit_id_on_two_cards_is_fine():
    two = catalog(benefit())
    other = copy.deepcopy(two["cards"][0])
    other["id"] = "other-card"
    two["cards"].append(other)
    assert catalog_errors(two) == []


def test_command_line(tmp_path, capsys):
    assert main(["validate", str(ROOT / "catalog.json")]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(catalog(benefit(category="Other"))))
    assert main(["validate", str(bad)]) == 1
    assert "INVALID" in capsys.readouterr().out
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert main(["validate", str(broken)]) == 1
