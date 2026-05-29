import logging
import httpx
from datetime import date

logger = logging.getLogger(__name__)

try:
    from facebook_business.adobjects.adaccount import AdAccount as FBAdAccount
    from facebook_business.api import FacebookAdsApi
    META_AVAILABLE = True
except ImportError:
    META_AVAILABLE = False

TIKTOK_API = "https://business-api.tiktok.com/open_api/v1.3"


def get_meta_creatives(credentials: dict, stat_date: date) -> list:
    if not META_AVAILABLE:
        return []
    try:
        FacebookAdsApi.init(access_token=credentials["access_token"])
        account = FBAdAccount(credentials["account_id"])

        params = {
            "time_range": {"since": str(stat_date), "until": str(stat_date)},
            "level": "ad",
            "limit": 20,
            "sort": ["spend_descending"],
        }
        fields = ["ad_id", "ad_name", "spend", "impressions", "clicks", "ctr", "actions"]
        insights = account.get_insights(params=params, fields=fields)

        results = []
        for row in insights:
            ad_id = row.get("ad_id", "")
            image_url = _get_meta_thumbnail(credentials["access_token"], ad_id)
            conversions = 0
            for a in row.get("actions", []):
                if a.get("action_type") in ("purchase", "lead", "complete_registration"):
                    conversions += int(a.get("value", 0))
            results.append({
                "ad_id":       ad_id,
                "ad_name":     row.get("ad_name", ""),
                "spend":       float(row.get("spend", 0)),
                "impressions": int(row.get("impressions", 0)),
                "clicks":      int(row.get("clicks", 0)),
                "ctr":         float(row.get("ctr", 0)),
                "conversions": conversions,
                "image_url":   image_url,
            })
        return results
    except Exception as e:
        logger.error(f"Meta creatives error: {e}")
        return []


def _get_meta_thumbnail(access_token: str, ad_id: str) -> str:
    try:
        resp = httpx.get(
            f"https://graph.facebook.com/v19.0/{ad_id}",
            params={"fields": "creative{thumbnail_url}", "access_token": access_token},
            timeout=5,
        )
        data = resp.json()
        return data.get("creative", {}).get("thumbnail_url", "")
    except Exception:
        return ""


def get_tiktok_creatives(credentials: dict, stat_date: date) -> list:
    try:
        headers = {
            "Access-Token": credentials["access_token"],
            "Content-Type": "application/json",
        }
        payload = {
            "advertiser_id": credentials["advertiser_id"],
            "report_type":   "BASIC",
            "dimensions":    ["ad_id"],
            "metrics":       ["spend", "impressions", "clicks", "ctr", "conversions"],
            "start_date":    str(stat_date),
            "end_date":      str(stat_date),
            "page_size":     20,
            "order_field":   "spend",
            "order_type":    "DESC",
        }
        resp = httpx.post(f"{TIKTOK_API}/report/integrated/get/", headers=headers, json=payload, timeout=15)
        data = resp.json()

        if data.get("code") != 0:
            return []

        results = []
        for row in data.get("data", {}).get("list", []):
            m = row.get("metrics", {})
            d = row.get("dimensions", {})
            ad_id = d.get("ad_id", "")
            image_url = _get_tiktok_thumbnail(credentials, ad_id)
            results.append({
                "ad_id":       ad_id,
                "ad_name":     m.get("ad_name", ad_id),
                "spend":       float(m.get("spend", 0) or 0),
                "impressions": int(m.get("impressions", 0) or 0),
                "clicks":      int(m.get("clicks", 0) or 0),
                "ctr":         float(m.get("ctr", 0) or 0),
                "conversions": int(m.get("conversions", 0) or 0),
                "image_url":   image_url,
            })
        return results
    except Exception as e:
        logger.error(f"TikTok creatives error: {e}")
        return []


def _get_tiktok_thumbnail(credentials: dict, ad_id: str) -> str:
    try:
        headers = {"Access-Token": credentials["access_token"], "Content-Type": "application/json"}
        payload = {
            "advertiser_id": credentials["advertiser_id"],
            "filters": {"ad_ids": [ad_id]},
            "fields": ["image_ids"],
        }
        resp = httpx.post(f"{TIKTOK_API}/ad/get/", headers=headers, json=payload, timeout=5)
        data = resp.json()
        ads = data.get("data", {}).get("list", [])
        if ads:
            image_ids = ads[0].get("image_ids", [])
            if image_ids:
                return _get_tiktok_image_url(credentials, image_ids[0])
        return ""
    except Exception:
        return ""


def _get_tiktok_image_url(credentials: dict, image_id: str) -> str:
    try:
        headers = {"Access-Token": credentials["access_token"], "Content-Type": "application/json"}
        payload = {
            "advertiser_id": credentials["advertiser_id"],
            "image_ids": [image_id],
        }
        resp = httpx.post(f"{TIKTOK_API}/file/image/ad/get/", headers=headers, json=payload, timeout=5)
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        if items:
            return items[0].get("url", "")
        return ""
    except Exception:
        return ""


CREATIVE_FETCHERS = {
    "meta":   get_meta_creatives,
    "tiktok": get_tiktok_creatives,
}


def fetch_creatives(platform: str, credentials: dict, stat_date: date) -> list:
    fn = CREATIVE_FETCHERS.get(platform)
    return fn(credentials, stat_date) if fn else []
