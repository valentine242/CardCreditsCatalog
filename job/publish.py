"""Put the new catalog.json where it belongs.

Safe changes only  -> commit straight to main (GitHub Pages publishes it).
Any big change     -> a pull request labelled "needs review"; the safe
                      changes from the same run ride along, so the published
                      catalog never half-updates.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config
from .validate import catalog_errors


def _run(*args: str, check: bool = True) -> str:
    done = subprocess.run(args, cwd=config.ROOT, text=True, capture_output=True)
    if check and done.returncode != 0:
        raise RuntimeError(f"`{' '.join(args)}` failed:\n{done.stdout}{done.stderr}".strip())
    return done.stdout.strip()


def catalog_changed() -> bool:
    return bool(_run("git", "status", "--porcelain", "--", "catalog.json"))


def _close_stale_review() -> None:
    """An older "needs review" pull request no longer matches the issuers'
    pages once a later check finds nothing big. Close it with a note."""
    open_prs = json.loads(_run(
        "gh", "pr", "list", "--repo", config.REPO, "--head", config.REVIEW_BRANCH,
        "--state", "open", "--json", "number", check=False) or "[]")
    for pr in open_prs:
        _run("gh", "pr", "close", str(pr["number"]), "--repo", config.REPO, "--comment",
             "Closed automatically: the latest check found nothing that needs review, "
             "so this older update no longer matches the issuers' pages.", check=False)
        print(f"Closed the outdated pull request #{pr['number']}.")


def _catalog_errors_on_disk() -> list[str]:
    try:
        return catalog_errors(json.loads(config.CATALOG_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"catalog.json can't be read: {exc}"]


def publish(big: bool, title: str, body: str, today: str) -> int:
    errors = _catalog_errors_on_disk()
    if errors:
        print("ERROR: catalog.json fails validation, so nothing is published:")
        for line in errors:
            print(f"  - {line}")
        return 1

    if not catalog_changed():
        if big:
            print("ERROR: the run found problems that need review, but there is no "
                  "catalog change to put in a pull request. See the summary above.")
            return 1
        print("Nothing changed; nothing to publish.")
        return 0

    start = _run("git", "rev-parse", "--abbrev-ref", "HEAD")
    if start != "main":
        print(f"ERROR: publishing starts from the main branch (now on '{start}').")
        return 1

    if not big:
        _run("git", "add", "catalog.json")
        _run("git", "commit", "-m", f"Catalog check {today}: safe changes only")
        _run("git", "push", "origin", "HEAD:main")
        print("Safe changes only: committed to main. GitHub Pages will publish them.")
        _close_stale_review()
        return 0

    try:
        _run("git", "checkout", "-B", config.REVIEW_BRANCH)
        _run("git", "add", "catalog.json")
        _run("git", "commit", "-m", title)
        _run("git", "push", "--force", "origin", config.REVIEW_BRANCH)
    finally:
        _run("git", "checkout", "main", check=False)

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
        body_file = f.name
    try:
        open_prs = json.loads(_run(
            "gh", "pr", "list", "--repo", config.REPO, "--head", config.REVIEW_BRANCH,
            "--state", "open", "--json", "number,url"))
        if open_prs:
            number = str(open_prs[0]["number"])
            _run("gh", "pr", "edit", number, "--repo", config.REPO, "--title", title,
                 "--body-file", body_file, "--add-label", config.REVIEW_LABEL)
            url = open_prs[0]["url"]
            print(f"Big changes: updated the open pull request {url}")
        else:
            url = _run("gh", "pr", "create", "--repo", config.REPO, "--base", "main",
                       "--head", config.REVIEW_BRANCH, "--title", title,
                       "--body-file", body_file, "--label", config.REVIEW_LABEL)
            print(f"Big changes: opened a pull request for review: {url}")
    finally:
        Path(body_file).unlink(missing_ok=True)
    return 0


def main() -> int:
    """Publish what the last `python -m job.update` produced."""
    try:
        result = json.loads((config.OUT_DIR / "result.json").read_text(encoding="utf-8"))
        body = (config.OUT_DIR / "summary.md").read_text(encoding="utf-8")
    except OSError:
        print("ERROR: nothing to publish. Run `python -m job.update` first.")
        return 1
    return publish(result["big"], result["title"], body, result["today"])


if __name__ == "__main__":
    sys.exit(main())
