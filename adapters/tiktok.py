import logging
import httpx
from datetime import date

logger = logging.getLogger(__name__)
TIKTOK_API = "https://business-api.tiktok.com/open_api/v1.3"


def get_tiktok_stats(credentials: dict, start_date: date, end_date: date) -> dict:
    try:
        headers = {
            "Access-Token":  credentials["access_token"],
            "Content-Type":  "application/json",
        }
        payload = {
            "advertiser_id": credentials["advertiser_id"],
            "report_type":   "BASIC",
            "dimensions":    ["stat_time_day"],
            "metrics":       ["spend", "impressions", "clicks", "ctr", "conversions"],
            "start_date":    str(start_date),
            "end_date":      str(end_date),
            "page_size":     100,
        }
        resp = httpx.post(f"{TIKTOK_API}/report/integrated/get/", headers=headers, json=payload, timeout=30)
        data = resp.json()

        if data.get("code") != 0:
            logger.error(f"TikTok error: {data.get('message')}")
            return _empty()

        totals = _empty()
        for row in data.get("data", {}).get("list", []):
            m = row.get("metrics", {})
            totals["impressions"] += int(m.get("impressions", 0) or 0)
            totals["clicks"]      += int(m.get("clicks", 0) or 0)
            totals["spend"]       += float(m.get("spend", 0) or 0)
            totals["conversions"] += int(m.get("conversions", 0) or 0)

        if totals["impressions"] > 0:
            totals["ctr"] = totals["clicks"] / totals["impressions"] * 100

        return totals

    except Exception as e:
        logger.error(f"TikTok unexpected: {e}")
        return _empty()


def _empty():
    return {"impressions": 0, "clicks": 0, "spend": 0.0, "ctr": 0.0, "conversions": 0}
