"""Get the readable text of an issuer page.

A plain download, plus a headless browser (Playwright / Chromium) for what
the page only shows after its JavaScript runs. A page that shows no benefit
text either way is reported, never guessed at.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from . import config

_SKIP_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "head")
_BLOCK_SIGNS = (
    "access denied", "are you a robot", "captcha", "request blocked",
    "enable javascript", "unusual activity",
)


@dataclass
class PageText:
    url: str
    text: str            # "" when nothing usable was found
    method: str          # "plain", "browser" or "none"
    note: str = ""       # why it failed / what happened

    @property
    def ok(self) -> bool:
        return self.method != "none"


def is_issuer_url(url: str) -> bool:
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == allowed or host.endswith("." + allowed) for allowed in config.ALLOWED_HOSTS
    )


def html_to_text(html: str) -> str:
    """Visible wording of a page, one line per block, in page order.
    Collapsed sections (accordions, footnotes) are kept: terms live there."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_SKIP_TAGS):
        tag.decompose()
    lines: list[str] = []
    for raw in soup.get_text(separator="\n").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return "\n".join(lines)


def has_benefit_text(text: str) -> bool:
    """Does this look like a real card page with its benefits on it?
    (Enough words, several dollar amounts, and the word "credit".)"""
    if len(text) < 1500:
        return False
    low = text.lower()
    if len(text) < 6000 and any(sign in low for sign in _BLOCK_SIGNS):
        return False
    dollar_amounts = len(re.findall(r"\$\s?\d", text))
    return dollar_amounts >= 3 and "credit" in low


def fetch_plain(url: str, timeout: int = 45) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    response.raise_for_status()
    if "charset" not in response.headers.get("Content-Type", "").lower():
        response.encoding = "utf-8"  # issuer pages are UTF-8; requests would guess Latin-1
    return response.text


def fetch_with_browser(url: str, timeout_ms: int = 60000) -> str:
    """The page's HTML after its JavaScript has run."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=config.USER_AGENT,
                locale="en-US",
                viewport={"width": 1280, "height": 2000},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except PlaywrightTimeout:
                pass  # busy pages never go quiet; the scroll below gives them time
            for _ in range(12):  # scroll down so lazily loaded sections appear
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(350)
            return page.content()
        finally:
            browser.close()


def _merge_texts(plain_text: str, browser_text: str) -> tuple[str, int]:
    """Plain text plus every line only the browser showed. Returns the text
    and how many of the added lines carry a dollar amount."""
    have = set(plain_text.splitlines())
    extra = [line for line in browser_text.splitlines() if line not in have]
    added_amounts = sum(1 for line in extra if re.search(r"\$\s?\d", line))
    if not extra:
        return plain_text, 0
    return plain_text + "\n" + "\n".join(extra), added_amounts


def get_page_text(url: str, plain=fetch_plain, browser=fetch_with_browser) -> PageText:
    """Read the page both ways and keep everything either one shows.

    Some issuer pages send part of their benefits in the first download and
    fill in the rest with JavaScript, so a plain download that "looks fine"
    can still be missing credits. The headless browser is therefore always
    tried as well; its extra lines are added to the plain text.

    method: "plain"          the plain download had it all
            "plain+browser"  the browser added lines with dollar amounts
            "browser"        only the browser gave benefit text
            "none"           no benefit text either way (a person must look)
    """
    if not is_issuer_url(url):
        return PageText(url, "", "none", "not an https page on an allowed issuer site")

    notes: list[str] = []
    plain_text = browser_text = ""
    try:
        plain_text = html_to_text(plain(url))
        if not has_benefit_text(plain_text):
            notes.append(f"plain download had no benefit text ({len(plain_text)} characters)")
            plain_text = ""
    except Exception as exc:
        notes.append(f"plain download failed: {type(exc).__name__}: {exc}")
    try:
        browser_text = html_to_text(browser(url))
        if not has_benefit_text(browser_text):
            notes.append(f"headless browser had no benefit text ({len(browser_text)} characters)")
            browser_text = ""
    except Exception as exc:
        notes.append(f"headless browser failed: {type(exc).__name__}: {str(exc).splitlines()[0]}")

    note = "; ".join(notes)
    if plain_text and browser_text:
        text, added_amounts = _merge_texts(plain_text, browser_text)
        if added_amounts:
            return PageText(url, text, "plain+browser",
                            f"the browser added {added_amounts} line(s) with dollar amounts")
        return PageText(url, text, "plain", note)
    if plain_text:
        return PageText(url, plain_text, "plain", note)
    if browser_text:
        return PageText(url, browser_text, "browser", note)
    return PageText(url, "", "none", note)
