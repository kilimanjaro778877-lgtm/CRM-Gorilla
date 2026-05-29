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
def dashboard(request: Request, period: str = "today", db: Session = Depends(get_db)):
    today = date.today()

    periods = {
        "today":     (today, today),
        "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
        "7d":        (today - timedelta(days=6), today),
        "30d":       (today - timedelta(days=29), today),
        "month":     (today.replace(day=1), today),
    }
    date_from, date_to = periods.get(period, periods["today"])
    prev_from = date_from - (date_to - date_from + timedelta(days=1))
    prev_to   = date_from - timedelta(days=1)

    accounts = db.query(AdAccount).filter(AdAccount.is_active == True).order_by(AdAccount.platform).all()

    rows = []
    totals = {"spend": 0, "impressions": 0, "clicks": 0, "conversions": 0}
    prev_totals = {"spend": 0}

    for acc in accounts:
        from sqlalchemy import func as sqlfunc
        cur = db.query(
            sqlfunc.sum(AdStats.spend).label("spend"),
            sqlfunc.sum(AdStats.impressions).label("impressions"),
            sqlfunc.sum(AdStats.clicks).label("clicks"),
            sqlfunc.sum(AdStats.conversions).label("conversions"),
        ).filter(
            AdStats.account_id == acc.id,
            AdStats.date >= date_from,
            AdStats.date <= date_to,
        ).first()

        prv = db.query(sqlfunc.sum(AdStats.spend)).filter(
            AdStats.account_id == acc.id,
            AdStats.date >= prev_from,
            AdStats.date <= prev_to,
        ).scalar() or 0

        spend    = float(cur.spend or 0)
        impr     = int(cur.impressions or 0)
        clicks   = int(cur.clicks or 0)
        convs    = int(cur.conversions or 0)
        ctr      = (clicks / impr * 100) if impr > 0 else 0
        pct_chg  = ((spend - prv) / prv * 100) if prv > 0 else None

        totals["spend"]       += spend
        totals["impressions"] += impr
        totals["clicks"]      += clicks
        totals["conversions"] += convs
        prev_totals["spend"]  += prv

        rows.append({
            "account": acc,
            "spend":   spend,
            "impr":    impr,
            "clicks":  clicks,
            "ctr":     ctr,
            "convs":   convs,
            "pct_chg": pct_chg,
            "status":  _status_val(spend, float(prv)),
            "icon":    PLATFORM_ICONS.get(acc.platform, "📊"),
        })

    total_ctr  = (totals["clicks"] / totals["impressions"] * 100) if totals["impressions"] > 0 else 0
    total_cpc  = (totals["spend"] / totals["clicks"]) if totals["clicks"] > 0 else 0
    total_cpm  = (totals["spend"] / totals["impressions"] * 1000) if totals["impressions"] > 0 else 0
    total_cpa  = (totals["spend"] / totals["conversions"]) if totals["conversions"] > 0 else 0
    total_pct  = ((totals["spend"] - prev_totals["spend"]) / prev_totals["spend"] * 100) if prev_totals["spend"] > 0 else None

    chart_data   = _chart_data(db, today, accounts)

    top_creatives = (
        db.query(AdCreative, AdAccount)
        .join(AdAccount, AdCreative.account_id == AdAccount.id)
        .filter(AdCreative.date >= date_from, AdCreative.date <= date_to)
        .order_by(AdCreative.spend.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(request, "dashboard.html", {
        "rows":           rows,
        "totals":         totals,
        "total_ctr":      total_ctr,
        "total_cpc":      total_cpc,
        "total_cpm":      total_cpm,
        "total_cpa":      total_cpa,
        "total_pct":      total_pct,
        "chart_data":     chart_data,
        "today":          today,
        "account_count":  len(accounts),
        "top_creatives":  top_creatives,
        "period":         period,
        "date_from":      date_from,
        "date_to":        date_to,
        "icons":          PLATFORM_ICONS,
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

def _status_val(spend: float, prev_spend: float) -> str:
    if prev_spend == 0:
        return "gray"
    threshold = float(os.getenv("ALERT_THRESHOLD_PCT", 30)) / 100
    drop = (prev_spend - spend) / prev_spend
    if drop > threshold:
        return "red"
    if drop > threshold / 2:
        return "yellow"
    return "green"


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
