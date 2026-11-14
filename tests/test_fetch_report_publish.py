import json

import pytest

from job import config, publish, report
from job.classify import BIG, SAFE, Change
from job.fetch import get_page_text, has_benefit_text, html_to_text, is_issuer_url
from tests.helpers import TODAY

URL = "https://creditcards.chase.com/some-card"
GOOD_HTML = "<html><head><title>t</title><script>var x='$999';</script></head><body>" + \
    "<h1>Card</h1><p>Get a $300 travel credit each year.</p><p>$10 monthly credit.</p>" + \
    "<div hidden>Terms: $5 minimum.</div>" + "".join(f"<p>More words about the card, part {i}.</p>" for i in range(80)) + "</body></html>"
SHELL_HTML = "<html><body><div id='root'></div><script>load()</script></body></html>"


def boom(url):
    raise RuntimeError("blocked")


def test_html_to_text_keeps_words_and_drops_code():
    text = html_to_text(GOOD_HTML)
    assert "$300 travel credit" in text and "Terms: $5 minimum." in text
    assert "$999" not in text and "var x" not in text


def test_plain_fetch_is_enough_when_the_browser_adds_nothing():
    page = get_page_text(URL, plain=lambda u: GOOD_HTML, browser=lambda u: GOOD_HTML)
    assert (page.method, page.ok) == ("plain", True)


def test_plain_text_still_used_when_the_browser_is_unavailable():
    page = get_page_text(URL, plain=lambda u: GOOD_HTML, browser=boom)
    assert page.method == "plain" and "headless browser failed" in page.note


def test_browser_adds_benefits_the_plain_download_lacks():
    richer = GOOD_HTML.replace("</body>", "<p>Receive a $120 credit for Global Entry.</p></body>")
    page = get_page_text(URL, plain=lambda u: GOOD_HTML, browser=lambda u: richer)
    assert page.method == "plain+browser"
    assert "$120 credit" in page.text and "$300 travel credit" in page.text
    assert page.text.count("$300 travel credit") == 1


def test_javascript_page_falls_back_to_the_browser():
    page = get_page_text(URL, plain=lambda u: SHELL_HTML, browser=lambda u: GOOD_HTML)
    assert page.method == "browser" and "$300" in page.text


def test_blocked_plain_fetch_falls_back_to_the_browser():
    assert get_page_text(URL, plain=boom, browser=lambda u: GOOD_HTML).method == "browser"


def test_page_with_no_text_either_way_is_flagged():
    page = get_page_text(URL, plain=lambda u: SHELL_HTML, browser=lambda u: SHELL_HTML)
    assert (page.method, page.ok, page.text) == ("none", False, "")
    assert "plain download" in page.note and "headless browser" in page.note
    assert get_page_text(URL, plain=boom, browser=boom).method == "none"


def test_bot_wall_is_not_benefit_text():
    wall = "Access Denied. " + "You don't have permission to see this credit page $1 $2 $3. " * 30
    assert not has_benefit_text(wall)


def test_only_issuer_sites_are_read():
    assert is_issuer_url("https://www.americanexpress.com/us/x")
    assert is_issuer_url("https://chase.com/x")
    for bad in ("https://www.nerdwallet.com/x", "https://notchase.com/x",
                "http://www.chase.com/x", "https://chase.com.evil.example/x"):
        assert not is_issuer_url(bad)
        assert get_page_text(bad, plain=lambda u: GOOD_HTML, browser=lambda u: GOOD_HTML).method == "none"


def test_sources_file_lists_15_cards_on_issuer_sites():
    cards = json.loads(config.SOURCES_PATH.read_text())["cards"]
    assert [c["id"] for c in cards] == [
        "chase-sapphire-reserve", "chase-united-club", "amex-platinum", "amex-gold",
        "amex-blue-cash-preferred", "amex-delta-reserve", "amex-marriott-brilliant",
        "chase-united-quest", "amex-hilton-aspire", "capital-one-venture-x",
        "citi-strata-elite", "chase-sapphire-preferred", "amex-business-platinum",
        "amex-delta-platinum", "amex-hilton-surpass"]
    for card in cards:
        assert card["name"] and card["issuer"] and card["urls"]
        assert all(is_issuer_url(u) for u in card["urls"])


# ------------------------------------------------------------------ report

BIG_ROW = Change(BIG, "amount changed", "Test Card", "Dining | Credit",
                 "value_usd: $10.00", "value_usd: $15.00", "https://chase.com/p")
SAFE_ROWS = [Change(SAFE, "checked again", "Test Card", "Hotel Credit", "2026-11-09", TODAY, "https://chase.com/p"),
             Change(SAFE, "details changed", "Test Card", "Hotel Credit", "Old words", "New words", "https://chase.com/p")]


def test_summary_has_the_review_table():
    body = report.summary_markdown([BIG_ROW, *SAFE_ROWS], TODAY)
    assert "| Card | Benefit | What changed | Old | New | Source |" in body
    assert "Dining \\| Credit" in body and "$15.00" in body
    assert "[issuer page](https://chase.com/p)" in body
    assert "Safe changes in the same update (2)" in body and "New words" in body
    assert "Not financial advice. Always confirm terms with your card issuer." in body
    assert "1 change(s) need review" in report.title([BIG_ROW], TODAY)


def test_safe_only_summary_and_length_cap():
    assert "Nothing needs review" in report.summary_markdown(SAFE_ROWS, TODAY)
    huge = report.summary_markdown([BIG_ROW] * 2000, TODAY)
    assert len(huge) < 65536 and "Files changed" in huge


# ----------------------------------------------------------------- publish

class FakeShell:
    def __init__(self, changed=True, branch="main", open_prs="[]"):
        self.calls, self.changed, self.branch, self.open_prs = [], changed, branch, open_prs

    def __call__(self, *args, check=True):
        self.calls.append(args)
        if args[:2] == ("git", "status"):
            return " M catalog.json" if self.changed else ""
        if args[:2] == ("git", "rev-parse"):
            return self.branch
        if args[:3] == ("gh", "pr", "list"):
            return self.open_prs
        if args[:3] == ("gh", "pr", "create"):
            return "https://github.com/x/y/pull/1"
        return ""

    def ran(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == prefix]


@pytest.fixture
def shell(monkeypatch):
    def make(**kw):
        fake = FakeShell(**kw)
        monkeypatch.setattr(publish, "_run", fake)
        return fake
    return make


def test_safe_run_commits_to_main_and_opens_no_pull_request(shell):
    sh = shell()
    assert publish.publish(False, "t", "b", TODAY) == 0
    assert sh.ran("git", "push") == [("git", "push", "origin", "HEAD:main")]
    assert not sh.ran("gh", "pr", "create") and not sh.ran("git", "checkout")


def test_big_run_opens_a_labelled_pull_request_and_never_pushes_main(shell):
    sh = shell()
    assert publish.publish(True, "title", "body", TODAY) == 0
    assert sh.ran("git", "push") == [("git", "push", "--force", "origin", "catalog-update")]
    create = sh.ran("gh", "pr", "create")[0]
    assert create[create.index("--label") + 1] == "needs review"
    assert create[create.index("--base") + 1] == "main"
    assert not sh.ran("gh", "pr", "merge")
    assert sh.calls.index(("git", "checkout", "main")) > sh.calls.index(("git", "checkout", "-B", "catalog-update"))


def test_big_run_updates_an_open_pull_request(shell):
    sh = shell(open_prs='[{"number": 7, "url": "https://github.com/x/y/pull/7"}]')
    assert publish.publish(True, "title", "body", TODAY) == 0
    assert sh.ran("gh", "pr", "edit") and not sh.ran("gh", "pr", "create")


def test_nothing_changed(shell):
    sh = shell(changed=False)
    assert publish.publish(False, "t", "b", TODAY) == 0
    assert publish.publish(True, "t", "b", TODAY) == 1  # problems but nothing to review
    assert not sh.ran("git", "push")


def test_publishing_only_starts_from_main(shell):
    sh = shell(branch="something-else")
    assert publish.publish(False, "t", "b", TODAY) == 1
    assert not sh.ran("git", "push")


def test_invalid_catalog_is_never_pushed(shell, monkeypatch):
    sh = shell()
    monkeypatch.setattr(publish, "_catalog_errors_on_disk", lambda: ["category: 'Other' is not allowed"])
    assert publish.publish(False, "t", "b", TODAY) == 1
    assert publish.publish(True, "t", "b", TODAY) == 1
    assert not sh.ran("git", "push") and not sh.ran("git", "commit")
