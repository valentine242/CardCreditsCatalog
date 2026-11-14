"""The no-API run: answers from files, checked against saved pages exactly like Claude's."""
import json

import pytest

from job import manual
from job.extract import ExtractionError
from job.fetch import PageText
from job.update import run
from job.validate import catalog_errors
from tests.helpers import HOTEL, NIGHT, PAGE, TODAY, URL, catalog, claim, sources


def _write_answers(folder, answers):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "test-card.json").write_text(json.dumps({"card": "test-card", "pages": answers}))


def test_saved_pages_are_read_back_unchanged(tmp_path):
    index = manual.save_pages(sources(), tmp_path, lambda url: PageText(url, PAGE, "plain", ""))
    assert index[0]["file"] == "test-card-0.txt"
    page = manual.saved_page_reader(tmp_path)(URL)
    assert page.ok and page.text == PAGE
    missing = manual.saved_page_reader(tmp_path)("https://www.americanexpress.com/other/")
    assert not missing.ok


def test_answers_go_through_the_same_checks(tmp_path):
    manual.save_pages(sources(), tmp_path / "pages", lambda url: PageText(url, PAGE, "plain", ""))
    invented = claim(name="Invented Credit", value_usd=99, evidence="earn up to $99 back every month")
    _write_answers(tmp_path / "answers", {URL: [claim(), claim(**HOTEL), claim(**NIGHT), invented]})
    result = run(catalog(), sources(), TODAY, manual.saved_page_reader(tmp_path / "pages"),
                 manual.FileExtractor(tmp_path / "answers"))
    names = [b["name"] for b in result.catalog["cards"][0]["benefits"]]
    assert "Invented Credit" not in names                      # its quote isn't on the page
    assert {"Dining Credit", "Hotel Credit", "Free Night Award"} <= set(names)
    assert result.big and catalog_errors(result.catalog) == []
    assert any("not backed by the page" in c.kind for c in result.changes)


def test_a_page_with_no_answer_is_never_read_as_empty(tmp_path):
    _write_answers(tmp_path, {})
    with pytest.raises(ExtractionError):
        manual.FileExtractor(tmp_path).extract({"id": "test-card"}, URL, PAGE, [])
    with pytest.raises(ExtractionError):
        manual.FileExtractor(tmp_path).extract({"id": "other-card"}, URL, PAGE, [])
