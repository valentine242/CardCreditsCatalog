"""Whatever Claude answers, the catalog only gets what the page itself states."""
from job.extract import ExtractionError, build_user_message, ground, output_schema
from job.update import run
from job.validate import catalog_errors
from tests.helpers import (HOTEL, NIGHT, PAGE, TODAY, URL, FakeClaude, benefit, catalog,
                           claim, pages, sources)

NO_AMOUNT_PAGE = """\
Test Card benefits
Dining Credit: earn statement credits monthly at partner restaurants. Enrollment required.
This credit card also includes lounge access. See terms for $0 liability and $5 fees and $1 minimums.
""" + "More about the card and its statement credit terms. " * 40


def go(old, answer, page=PAGE):
    return run(old, sources(), TODAY, pages({URL: page}), FakeClaude({URL: answer}))


def test_page_without_an_amount_yields_no_amount():
    answer = [claim(value_usd=None, value_text=None,
                    evidence="earn statement credits monthly at partner restaurants")]
    result = go(catalog(benefit()), answer, NO_AMOUNT_PAGE)
    out = result.catalog["cards"][0]["benefits"][0]
    assert out["value_usd"] is None and out["value_text"] == ""
    assert result.big  # the amount went away: a person must look
    assert catalog_errors(result.catalog) == []


def test_amount_the_page_does_not_state_is_rejected():
    answer = [claim(value_usd=10, evidence="earn statement credits monthly at partner restaurants")]
    result = go(catalog(benefit(value_usd=25.0, value_text="$25.00")), answer, NO_AMOUNT_PAGE)
    kept = result.catalog["cards"][0]["benefits"][0]
    assert (kept["value_usd"], kept["last_verified"]) == (25.0, "2026-11-09")  # untouched
    assert any("not backed by the page" in c.kind for c in result.changes)
    assert result.big


def test_quote_that_is_not_on_the_page_is_rejected():
    grounded = ground([claim(value_usd=50, evidence="get $50 back every month on dining")],
                      PAGE, URL)
    assert grounded.benefits == [] and len(grounded.rejected) == 1


def test_amount_must_be_in_the_quote_itself():
    # $200 is on the page, but not in the quote offered for this benefit
    grounded = ground([claim(value_usd=200)], PAGE, URL)
    assert grounded.benefits == []


def test_dollar_wording_without_a_number_is_rejected():
    grounded = ground([claim(value_usd=None, value_text="$10 a month")], PAGE, URL)
    assert grounded.benefits == []


def test_stated_amount_is_accepted_and_formatted_by_code():
    grounded = ground([claim(value_text="about ten dollars")], PAGE, URL)
    assert grounded.rejected == []
    assert grounded.benefits[0]["value_usd"] == 10.0
    assert grounded.benefits[0]["value_text"] == "$10.00"
    assert grounded.benefits[0]["source_url"] == URL


def test_yearly_total_split_into_stated_windows_is_accepted():
    text = PAGE + "Get $300 in statement credits each year, given monthly.\n"
    ok = ground([claim(value_usd=25, evidence="Get $300 in statement credits each year, given monthly")],
                text, URL)
    assert ok.benefits[0]["value_usd"] == 25.0
    bad = ground([claim(value_usd=30, evidence="Get $300 in statement credits each year, given monthly")],
                 text, URL)
    assert bad.benefits == []


def test_quote_matching_ignores_spacing_case_and_marks():
    grounded = ground([claim(evidence="Earn up to  $10 in Statement Credits\nmonthly at partner restaurants.")],
                      PAGE, URL)
    assert len(grounded.benefits) == 1


def test_non_dollar_perk_keeps_null_amount():
    grounded = ground([claim(**NIGHT)], PAGE, URL)
    assert grounded.benefits[0]["value_usd"] is None
    assert grounded.benefits[0]["value_text"] == "1 night"


def test_end_date_kept_only_when_the_page_spells_it_out():
    text = PAGE + "Limited offer: get $50 back on one booking made by December 31, 2026.\n"
    offer = dict(name="Booking offer", value_usd=50, period="One time", category="Travel",
                 evidence="get $50 back on one booking made by December 31, 2026")
    assert ground([claim(**offer, end_date="2026-12-31")], text, URL).benefits[0]["end_date"] == "2026-12-31"
    assert ground([claim(**offer, end_date="2027-06-30")], text, URL).benefits[0]["end_date"] is None
    assert ground([claim(**offer, end_date="end of year")], text, URL).benefits[0]["end_date"] is None
    # never on a repeating benefit
    assert ground([claim(end_date="2026-12-31")], text, URL).benefits[0]["end_date"] is None


def test_values_outside_the_allowed_lists_are_rejected():
    assert ground([claim(category="Other")], PAGE, URL).benefits == []
    assert ground([claim(period="Weekly")], PAGE, URL).benefits == []
    assert ground([claim(name=" ")], PAGE, URL).benefits == []
    assert ground([claim(value_usd=-10)], PAGE, URL).benefits == []


def test_model_is_not_shown_catalog_amounts():
    message = build_user_message({"name": "Test Card", "issuer": "Amex"}, URL, "PAGE WORDS",
                                 [benefit(value_usd=987.0, value_text="$987.00"),
                                  benefit(id="gone", status="removed")])
    assert "987" not in message and "dining-credit" in message
    assert '"gone"' not in message and "PAGE WORDS" in message


def test_output_schema_is_strict():
    item = output_schema()["properties"]["benefits"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])


def test_a_failed_claude_answer_changes_nothing_for_that_card():
    old = catalog(benefit())
    result = go(old, ExtractionError("Claude's answer was cut off."))
    assert result.catalog["cards"] == old["cards"]
    assert result.big
