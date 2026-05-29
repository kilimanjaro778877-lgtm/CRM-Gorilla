from datetime import date

from adapters.meta import get_meta_stats
from adapters.google_ads import get_google_stats
from adapters.tiktok import get_tiktok_stats

FETCHERS = {
    "meta": get_meta_stats,
    "google": get_google_stats,
    "tiktok": get_tiktok_stats,
}

MANUAL_PLATFORMS = {"telegram", "trafficjunky", "manual"}

PLATFORM_LABELS = {
    "meta":         "Meta Ads",
    "google":       "Google Ads",
    "tiktok":       "TikTok Ads",
    "telegram":     "Telegram Ads",
    "trafficjunky": "TrafficJunky",
    "manual":       "Другое",
}

PLATFORM_ICONS = {
    "meta":         "📘",
    "google":       "🔍",
    "tiktok":       "🎵",
    "telegram":     "✈️",
    "trafficjunky": "🔞",
    "manual":       "📊",
}

# Fields shown in the Add Account form per platform
PLATFORM_FIELDS = {
    "meta": [
        {"name": "access_token", "label": "Access Token",            "type": "text"},
        {"name": "account_id",   "label": "Ad Account ID (act_xxx)", "type": "text"},
    ],
    "google": [
        {"name": "developer_token", "label": "Developer Token",               "type": "text"},
        {"name": "client_id",       "label": "Client ID",                     "type": "text"},
        {"name": "client_secret",   "label": "Client Secret",                 "type": "password"},
        {"name": "refresh_token",   "label": "Refresh Token",                 "type": "text"},
        {"name": "customer_id",     "label": "Customer ID (без дефисов)",     "type": "text"},
    ],
    "tiktok": [
        {"name": "access_token",   "label": "Access Token",   "type": "text"},
        {"name": "advertiser_id",  "label": "Advertiser ID",  "type": "text"},
    ],
    "telegram":     [],
    "trafficjunky": [],
    "manual":       [],
}


def fetch_stats(platform: str, credentials: dict, start_date: date, end_date: date) -> dict:
    fn = FETCHERS.get(platform)
    if fn:
        return fn(credentials, start_date, end_date)
    return {"impressions": 0, "clicks": 0, "spend": 0.0, "ctr": 0.0, "conversions": 0}
