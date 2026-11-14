"""The whole weekly run, with fake pages and a fake Claude."""
import pytest

from job import update
from job.classify import BIG, SAFE
from job.extract import FatalExtractionError
from job.update import dump_catalog, run
from job.validate import catalog_errors
from tests.helpers import (HOTEL, NIGHT, PAGE, TODAY, URL, FakeClaude, benefit, catalog,
                           claim, pages, sources, seed)

URL2 = "https://www.americanexpress.com/us/credit-cards/card/test-card/terms/"
ALL = [claim(existing_id="dining-credit"), claim(**HOTEL), claim(**NIGHT)]
FULL = catalog(
    benefit(),
    benefit(id="hotel-credit", name="Hotel Credit", category="Hotels", value_text="$200.00",
            value_usd=200.0, period="Annual", setup_step=None, details="Prepaid bookings."),
    benefit(id="free-night-award", name="Free Night Award", category="Hotels",
            value_text="1 night", value_usd=None, period="Anniversary", setup_step=None,
            details=None),
)


def go(old, answer, page=PAGE, src=None):
    return run(old, src or sources(), TODAY, pages({URL: page}), FakeClaude({URL: answer}))


def test_unchanged_page_is_a_safe_run():
    result = go(FULL, ALL)
    assert not result.big
    assert {c.severity for c in result.changes} == {SAFE}
    assert all(b["last_verified"] == TODAY and b["status"] == "verified"
               for b in result.catalog["cards"][0]["benefits"])
    assert result.catalog["generated"] == TODAY
    assert catalog_errors(result.catalog) == []


def test_changed_amount_is_big():
    page = PAGE.replace("up to $10 in", "up to $15 in")
    answer = [claim(existing_id="dining-credit", value_usd=15,
                    evidence="earn up to $15 in statement credits monthly"),
              claim(**HOTEL), claim(**NIGHT)]
    result = go(FULL, answer, page)
    assert result.big
    assert result.catalog["cards"][0]["benefits"][0]["value_usd"] == 15.0


def test_benefit_gone_from_the_page_is_kept_as_removed_and_is_big():
    result = go(FULL, [claim(existing_id="dining-credit"), claim(**NIGHT)])
    by_id = {b["id"]: b for b in result.catalog["cards"][0]["benefits"]}
    assert list(by_id) == ["dining-credit", "hotel-credit", "free-night-award"]
    assert by_id["hotel-credit"]["status"] == "removed"
    assert [c.kind for c in result.changes if c.severity == BIG] == ["benefit removed"]


def test_new_card_is_added_and_is_big():
    result = go(FULL, ALL, src=sources(card_id="brand-new"))
    assert [c["id"] for c in result.catalog["cards"]] == ["test-card", "brand-new"]
    assert [b["id"] for b in result.catalog["cards"][1]["benefits"]] == \
           ["dining-credit", "hotel-credit", "free-night-award"]
    assert result.catalog["cards"][0] == FULL["cards"][0]
    assert "new card" in [c.kind for c in result.changes]
    assert result.big


def test_page_that_yields_nothing_is_big_and_touches_nothing():
    result = run(FULL, sources(), TODAY, pages({URL: None}), FakeClaude({}))
    assert result.catalog["cards"] == FULL["cards"]
    assert [c.kind for c in result.changes if c.severity == BIG] == ["page yielded nothing"]
    assert result.changes[-1].source_url == URL


def test_empty_answer_never_removes_every_benefit():
    result = go(FULL, [])
    assert result.catalog["cards"] == FULL["cards"]
    assert result.big


def test_new_card_whose_page_fails_is_not_added():
    result = run(FULL, sources(card_id="brand-new"), TODAY, pages({URL: None}), FakeClaude({}))
    assert [c["id"] for c in result.catalog["cards"]] == ["test-card"]
    assert result.big


def test_one_bad_page_of_two_blocks_removals():
    src = sources(urls=(URL, URL2))
    result = run(FULL, src, TODAY, pages({URL: PAGE, URL2: None}),
                 FakeClaude({URL: [claim(existing_id="dining-credit")]}))
    statuses = [b["status"] for b in result.catalog["cards"][0]["benefits"]]
    assert "removed" not in statuses
    assert result.big


def test_same_benefit_on_two_pages_counts_once_with_first_source():
    src = sources(urls=(URL, URL2))
    fake = FakeClaude({URL: ALL, URL2: [claim(existing_id="dining-credit")]})
    result = run(FULL, src, TODAY, pages({URL: PAGE, URL2: PAGE}), fake)
    benefits = result.catalog["cards"][0]["benefits"]
    assert len(benefits) == 3 and benefits[0]["source_url"] == URL
    assert not result.big


def test_card_that_would_break_the_schema_is_left_unchanged(monkeypatch):
    real = update.catalog_errors
    monkeypatch.setattr(update, "catalog_errors",
                        lambda c: ["made-up failure"] if c["cards"][0]["benefits"][0]["last_verified"] == TODAY else real(c))
    result = go(FULL, ALL)
    assert result.catalog["cards"] == FULL["cards"]
    assert any(c.kind.startswith("validation failure") for c in result.changes)
    assert result.big


def test_cards_not_in_sources_are_left_alone():
    old = seed()
    result = go(old, ALL, src=sources(card_id="brand-new"))
    assert result.catalog["cards"][:9] == old["cards"]
    assert catalog_errors(result.catalog) == []


def test_claude_sees_the_page_and_existing_ids():
    fake = FakeClaude({URL: ALL})
    run(FULL, sources(), TODAY, pages({URL: PAGE}), fake)
    call = fake.calls[0]
    assert call["page_text"] == PAGE and call["url"] == URL
    assert [b["id"] for b in call["existing"]][0] == "dining-credit"


def test_missing_key_stops_with_a_readable_message(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    target = tmp_path / "catalog.json"
    target.write_text(dump_catalog(FULL))
    monkeypatch.setattr(update.config, "CATALOG_PATH", target)
    before = target.read_text()
    assert update.main([]) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().out
    assert target.read_text() == before


def test_fatal_errors_stop_the_run():
    with pytest.raises(FatalExtractionError):
        go(FULL, FatalExtractionError("bad key"))


def test_written_file_is_valid_json_ending_in_newline():
    text = dump_catalog(go(FULL, ALL).catalog)
    assert text.endswith("}\n") and "\\u" not in text
