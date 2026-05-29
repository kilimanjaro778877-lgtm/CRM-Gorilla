import logging
from datetime import date
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.api import FacebookAdsApi

logger = logging.getLogger(__name__)


def get_meta_stats(credentials: dict, start_date: date, end_date: date) -> dict:
    try:
        FacebookAdsApi.init(access_token=credentials["access_token"])
        account = AdAccount(credentials["account_id"])

        params = {
            "time_range": {"since": str(start_date), "until": str(end_date)},
            "level": "account",
        }
        fields = ["impressions", "clicks", "spend", "ctr", "actions"]
        insights = account.get_insights(params=params, fields=fields)

        if not insights:
            return _empty()

        row = insights[0]
        conversions = 0
        for action in row.get("actions", []):
            if action.get("action_type") in ("purchase", "lead", "complete_registration"):
                conversions += int(action.get("value", 0))

        return {
            "impressions": int(row.get("impressions", 0)),
            "clicks":      int(row.get("clicks", 0)),
            "spend":       float(row.get("spend", 0)),
            "ctr":         float(row.get("ctr", 0)),
            "conversions": conversions,
        }

    except Exception as e:
        logger.error(f"Meta error: {e}")
        return _empty()


def _empty():
    return {"impressions": 0, "clicks": 0, "spend": 0.0, "ctr": 0.0, "conversions": 0}
