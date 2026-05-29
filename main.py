import os
import json
import logging
from datetime import date, timedelta

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import AdAccount, AdStats, AdCreative
from adapters import PLATFORM_LABELS, PLATFORM_ICONS, PLATFORM_FIELDS, MANUAL_PLATFORMS
from scheduler import start_scheduler, run_sync, sync_account

logging.basicConfig(level=logging.INFO)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ads Gorilla")
_jinja_env = Environment(loader=FileSystemLoader("templates"), cache_size=0, auto_reload=True)
templates = Jinja2Templates(env=_jinja_env)


@app.on_event("startup")
def on_startup():
    start_scheduler()


# ── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    yesterday = today - timedelta(days=1)

    accounts = db.query(AdAccount).filter(AdAccount.is_active == True).order_by(AdAccount.platform).all()

    rows = []
    totals_today = {"spend": 0, "impressions": 0, "clicks": 0, "conversions": 0}

    for acc in accounts:
        t = db.query(AdStats).filter(AdStats.account_id == acc.id, AdStats.date == today).first()
        y = db.query(AdStats).filter(AdStats.account_id == acc.id, AdStats.date == yesterday).first()
        status = _status(t, y)

        if t:
            totals_today["spend"]       += t.spend
            totals_today["impressions"] += t.impressions
            totals_today["clicks"]      += t.clicks
            totals_today["conversions"] += t.conversions

        rows.append({
            "account": acc,
            "today":   t,
            "yesterday": y,
            "status":  status,
            "icon":    PLATFORM_ICONS.get(acc.platform, "📊"),
        })

    total_ctr = (
        totals_today["clicks"] / totals_today["impressions"] * 100
        if totals_today["impressions"] > 0 else 0
    )

    chart_data = _chart_data(db, today, accounts)

    top_creatives = (
        db.query(AdCreative, AdAccount)
        .join(AdAccount, AdCreative.account_id == AdAccount.id)
        .filter(AdCreative.date == today)
        .order_by(AdCreative.spend.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(request, "dashboard.html", {
        "rows":           rows,
        "totals":         totals_today,
        "total_ctr":      total_ctr,
        "chart_data":     chart_data,
        "today":          today,
        "account_count":  len(accounts),
        "top_creatives":  top_creatives,
    })


# ── Accounts management ────────────────────────────────────────────────────

@app.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request, db: Session = Depends(get_db)):
    accounts = db.query(AdAccount).order_by(AdAccount.created_at.desc()).all()
    return templates.TemplateResponse(request, "accounts.html", {
        "accounts":       accounts,
        "platform_labels": PLATFORM_LABELS,
        "platform_icons":  PLATFORM_ICONS,
        "platform_fields": PLATFORM_FIELDS,
        "platforms":       list(PLATFORM_LABELS.keys()),
    })


@app.post("/accounts/add")
async def add_account(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    platform = form["platform"]
    name     = form["name"]

    fields = PLATFORM_FIELDS.get(platform, [])
    credentials = {f["name"]: form.get(f["name"], "") for f in fields}

    db.add(AdAccount(name=name, platform=platform, credentials=credentials))
    db.commit()
    return RedirectResponse("/accounts", status_code=303)


@app.post("/accounts/{account_id}/delete")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(AdAccount).filter(AdAccount.id == account_id).first()
    if not acc:
        raise HTTPException(404)
    db.delete(acc)
    db.commit()
    return RedirectResponse("/accounts", status_code=303)


@app.post("/accounts/{account_id}/toggle")
def toggle_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(AdAccount).filter(AdAccount.id == account_id).first()
    if not acc:
        raise HTTPException(404)
    acc.is_active = not acc.is_active
    db.commit()
    return RedirectResponse("/accounts", status_code=303)


@app.post("/accounts/{account_id}/sync")
def sync_one(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(AdAccount).filter(AdAccount.id == account_id).first()
    if not acc:
        raise HTTPException(404)
    sync_account(acc)
    return {"ok": True}


# ── Manual stats (Telegram, TrafficJunky, etc.) ────────────────────────────

@app.post("/manual-stats")
def manual_stats(
    account_id:  int   = Form(...),
    date_str:    str   = Form(...),
    impressions: int   = Form(...),
    clicks:      int   = Form(...),
    spend:       float = Form(...),
    db: Session = Depends(get_db),
):
    stat_date = date.fromisoformat(date_str)
    ctr = (clicks / impressions * 100) if impressions > 0 else 0.0

    existing = db.query(AdStats).filter(
        AdStats.account_id == account_id,
        AdStats.date == stat_date,
    ).first()

    if existing:
        existing.impressions = impressions
        existing.clicks      = clicks
        existing.spend       = spend
        existing.ctr         = ctr
    else:
        db.add(AdStats(
            account_id=account_id, date=stat_date,
            impressions=impressions, clicks=clicks, spend=spend, ctr=ctr,
        ))

    db.commit()
    return RedirectResponse("/", status_code=303)


# ── Global sync ────────────────────────────────────────────────────────────

@app.post("/sync")
def global_sync():
    run_sync()
    return {"ok": True}


# ── Helpers ────────────────────────────────────────────────────────────────

def _status(today, yesterday) -> str:
    if not today or not yesterday or yesterday.spend == 0:
        return "gray"
    threshold = float(os.getenv("ALERT_THRESHOLD_PCT", 30)) / 100
    drop = (yesterday.spend - today.spend) / yesterday.spend
    if drop > threshold:
        return "red"
    if drop > threshold / 2:
        return "yellow"
    return "green"


def _chart_data(db: Session, today: date, accounts: list) -> dict:
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]

    datasets = []
    palette = {
        "meta":         "#1877f2",
        "google":       "#ea4335",
        "tiktok":       "#ff0050",
        "telegram":     "#29b6f6",
        "trafficjunky": "#ff6d00",
        "manual":       "#ab47bc",
    }

    for acc in accounts:
        rows = {
            r.date: r.spend
            for r in db.query(AdStats).filter(
                AdStats.account_id == acc.id,
                AdStats.date >= days[0],
                AdStats.date <= today,
            ).all()
        }
        color = palette.get(acc.platform, "#00e676")
        datasets.append({
            "label":           acc.name,
            "data":            [round(rows.get(d, 0), 2) for d in days],
            "borderColor":     color,
            "backgroundColor": color + "18",
            "tension":         0.4,
            "fill":            True,
            "pointRadius":     4,
        })

    return {
        "labels":   [str(d) for d in days],
        "datasets": datasets,
    }
