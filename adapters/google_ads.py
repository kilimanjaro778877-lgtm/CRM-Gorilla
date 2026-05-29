import logging
from datetime import date
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

logger = logging.getLogger(__name__)


def get_google_stats(credentials: dict, start_date: date, end_date: date) -> dict:
    try:
        config = {
            "developer_token": credentials["developer_token"],
            "client_id":       credentials["client_id"],
            "client_secret":   credentials["client_secret"],
            "refresh_token":   credentials["refresh_token"],
            "use_proto_plus":  True,
        }
        customer_id = credentials["customer_id"]

        client = GoogleAdsClient.load_from_dict(config)
        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.ctr,
                metrics.conversions
            FROM customer
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """

        response = ga_service.search(customer_id=customer_id, query=query)
        totals = _empty()
        n = 0

        for row in response:
            totals["impressions"] += row.metrics.impressions
            totals["clicks"]      += row.metrics.clicks
            totals["spend"]       += row.metrics.cost_micros / 1_000_000
            totals["ctr"]         += row.metrics.ctr * 100
            totals["conversions"] += int(row.metrics.conversions)
            n += 1

        if n > 0:
            totals["ctr"] /= n

        return totals

    except GoogleAdsException as e:
        logger.error(f"Google Ads error: {e}")
        return _empty()
    except Exception as e:
        logger.error(f"Google unexpected: {e}")
        return _empty()


def _empty():
    return {"impressions": 0, "clicks": 0, "spend": 0.0, "ctr": 0.0, "conversions": 0}
