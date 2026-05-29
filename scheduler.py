import logging
from datetime import date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

from database import SessionLocal
from models import AdAccount, AdStats
from adapters import fetch_stats, MANUAL_PLATFORMS
from alerts import check_and_alert

logger = logging.getLogger(__name__)


def sync_account(account: AdAccount):
    if account.platform in MANUAL_PLATFORMS:
        return

    today = date.today()
    yesterday = today - timedelta(days=1)
    db = SessionLocal()

    try:
        stats = fetch_stats(account.platform, account.credentials, today, today)

        existing = db.query(AdStats).filter(
            AdStats.account_id == account.id,
            AdStats.date == today,
        ).first()

        if existing:
            for k, v in stats.items():
                setattr(existing, k, v)
        else:
            db.add(AdStats(account_id=account.id, date=today, **stats))

        db.commit()
        logger.info(f"Synced [{account.name}] spend=${stats['spend']:.2f}")

        prev = db.query(AdStats).filter(
            AdStats.account_id == account.id,
            AdStats.date == yesterday,
        ).first()

        if prev:
            check_and_alert(
                account.name, account.platform, stats,
                {"spend": prev.spend, "ctr": prev.ctr, "clicks": prev.clicks},
            )

    except Exception as e:
        logger.error(f"Sync failed [{account.name}]: {e}")
        db.rollback()
    finally:
        db.close()


def run_sync():
    db = SessionLocal()
    try:
        accounts = db.query(AdAccount).filter(AdAccount.is_active == True).all()
    finally:
        db.close()

    logger.info(f"Syncing {len(accounts)} accounts...")
    for acc in accounts:
        sync_account(acc)


def start_scheduler():
    import os
    interval = int(os.getenv("CHECK_INTERVAL_HOURS", 2))
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(run_sync, "interval", hours=interval, id="sync_all")
    scheduler.start()
    logger.info(f"Scheduler started, interval={interval}h")
    return scheduler
