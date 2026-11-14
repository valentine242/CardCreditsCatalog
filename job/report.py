"""The plain-English summary shown in the pull request and the Actions run."""
from __future__ import annotations

from .classify import BIG, SAFE, Change

MAX_BODY = 60000  # GitHub's limit for a pull request description is 65,536
_WORDING = {"name reworded", "setup step changed", "details changed"}


def _cell(text: str, limit: int = 220) -> str:
    text = " ".join(str(text).split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _link(url: str) -> str:
    return f"[issuer page]({url})" if url else ""


def _big_table(changes: list[Change]) -> list[str]:
    lines = ["| Card | Benefit | What changed | Old | New | Source |",
             "|---|---|---|---|---|---|"]
    for c in changes:
        lines.append(f"| {_cell(c.card)} | {_cell(c.benefit)} | {_cell(c.kind)} | "
                     f"{_cell(c.old)} | {_cell(c.new)} | {_link(c.source_url)} |")
    return lines


def _safe_table(changes: list[Change]) -> list[str]:
    """One row per benefit: what was refreshed, and old → new for wording."""
    grouped: dict[tuple[str, str], list[Change]] = {}
    for c in changes:
        grouped.setdefault((c.card, c.benefit), []).append(c)
    lines = ["| Card | Benefit | What changed | Old | New | Source |",
             "|---|---|---|---|---|---|"]
    for (card, benefit), group in grouped.items():
        wording = [c for c in group if c.kind in _WORDING or c.kind.startswith("card ")]
        kinds = ", ".join(dict.fromkeys(c.kind for c in group))
        old = "; ".join(c.old for c in wording)
        new = "; ".join(c.new for c in wording)
        link = next((c.source_url for c in group if c.source_url), "")
        lines.append(f"| {_cell(card)} | {_cell(benefit)} | {_cell(kinds)} | "
                     f"{_cell(old)} | {_cell(new)} | {_link(link)} |")
    return lines


def summary_markdown(changes: list[Change], today: str) -> str:
    big = [c for c in changes if c.severity == BIG]
    safe = [c for c in changes if c.severity == SAFE]
    out: list[str] = [f"## Catalog check, {today}", ""]
    if big:
        out += [
            f"**{len(big)} change(s) need your review.** Open each issuer page, "
            "check the row against it, then merge this pull request to publish. "
            "Merging is your approval. If a row looks wrong, close the pull "
            "request instead; nothing is published.",
            "",
            *_big_table(big),
            "",
        ]
    else:
        out += ["Nothing needs review. Only safe changes (wording and "
                "\"last checked\" dates) were found and published.", ""]
    if safe:
        out += [
            "<details><summary>Safe changes in the same update "
            f"({len(safe)})</summary>",
            "",
            *_safe_table(safe),
            "",
            "</details>",
            "",
        ]
    out += ["Facts come only from the issuers' own pages. Not financial advice. "
            "Always confirm terms with your card issuer."]
    body = "\n".join(out) + "\n"
    if len(body) > MAX_BODY:
        cut = body[:MAX_BODY].rsplit("\n", 1)[0]
        body = (cut + "\n\n</details>\n\n_The table was too long to show in full. "
                "See the **Files changed** tab for every change._\n")
    return body


def title(changes: list[Change], today: str) -> str:
    big = sum(1 for c in changes if c.severity == BIG)
    return f"Catalog update {today}: {big} change(s) need review"
