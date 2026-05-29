import os
import asyncio
import logging
from telegram import Bot

logger = logging.getLogger(__name__)

PLATFORM_ICONS = {
    "meta": "📘", "google": "🔍", "tiktok": "🎵",
    "telegram": "✈️", "trafficjunky": "🔞", "manual": "📊",
}


async def _send(text: str):
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
    await bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=text, parse_mode="HTML")


def send_alert(text: str):
    try:
        asyncio.run(_send(text))
    except Exception as e:
        logger.error(f"Telegram send error: {e}")


def check_and_alert(account_name: str, platform: str, today: dict, yesterday: dict):
    threshold = float(os.getenv("ALERT_THRESHOLD_PCT", 30)) / 100
    issues = []

    def _check(key, label, fmt):
        prev, curr = yesterday.get(key, 0), today.get(key, 0)
        if prev > 0:
            drop = (prev - curr) / prev
            if drop > threshold:
                issues.append(f"{label}: <b>{fmt(prev)}</b> → <b>{fmt(curr)}</b> (-{drop*100:.0f}%)")

    _check("spend",  "💸 Расход",  lambda v: f"${v:.2f}")
    _check("ctr",    "📉 CTR",     lambda v: f"{v:.2f}%")
    _check("clicks", "🖱 Клики",   lambda v: str(int(v)))

    if issues:
        icon = PLATFORM_ICONS.get(platform, "📊")
        msg = f"🔴 <b>ПРОСАДКА | {icon} {account_name}</b>\n\n" + "\n".join(issues)
        send_alert(msg)
        logger.info(f"Alert sent: {account_name}")
