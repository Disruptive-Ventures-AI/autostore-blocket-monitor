import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
GRACE_GW_API_KEY = os.environ.get("GRACE_GW_API_KEY", "")
TRIGGER_API_KEY = os.environ.get("TRIGGER_API_KEY", "")
DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/blocket.db")
EMAIL_RECIPIENTS = [
    r.strip()
    for r in os.environ.get(
        "EMAIL_RECIPIENTS",
        "erik+blocket@autostoresverige.com,serge+autostore@lachapelle.se",
    ).split(",")
    if r.strip()
]
EMAIL_FROM = os.environ.get("EMAIL_FROM", "blocket@autostoresverige.com")

BLOCKET_API_URL = "https://blocket-api.se/v1/search/car"
GRACE_PROXY_URL = "https://grace-gw.dvbrain.ai/fetch"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

BLOCKET_PAGE_DELAY_S = 0.5
AD_PAGE_FETCH_DELAY_S = 0.2
BLOCKET_API_TIMEOUT_S = 30
AD_PAGE_FETCH_TIMEOUT_S = 15
EMAIL_BATCH_SIZE = 20
EMAIL_BATCH_DELAY_S = 2.0
EMPTY_EMAIL_THROTTLE_HOURS = 4
MAX_PAGES = 5
YEAR_FROM = 2010

PASSENGER_MILEAGE_LIMIT_KM = 200_000
MIL_THRESHOLD = 50_000
