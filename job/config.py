"""Settings for the update job. Change things here, nowhere else."""
from pathlib import Path

# The one place the Claude model is named.
CLAUDE_MODEL = "claude-opus-5-5"
# How hard the model works on each page (low | medium | high | xhigh | max).
CLAUDE_EFFORT = "high"
CLAUDE_MAX_TOKENS = 16000

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "catalog.json"
SOURCES_PATH = ROOT / "sources.json"
SCHEMA_PATH = ROOT / "schema" / "catalog.schema.json"
OUT_DIR = ROOT / "out"   # run summary handed from job.update to job.publish (git-ignored)

REPO = "valentine242/CardCreditsCatalog"
REVIEW_LABEL = "needs review"
REVIEW_BRANCH = "catalog-update"

# Only these sites may be listed in sources.json.
ALLOWED_HOSTS = ("chase.com", "americanexpress.com", "capitalone.com", "citi.com")

CATEGORIES = [
    "Dining", "Food delivery", "Rideshare", "Hotels", "Airlines & flights",
    "Travel", "Streaming & entertainment", "Shopping & memberships",
    "Fitness & wellness",
]
PERIODS = ["Monthly", "Quarterly", "Twice a year", "Annual", "Anniversary", "One time"]

CATALOG_NOTE = (
    "Updated automatically from the card issuers' own pages. Each benefit lists "
    "its source page and the date it was last checked. Not financial advice. "
    "Always confirm terms with your card issuer."
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Safari/605.1.15"
)
