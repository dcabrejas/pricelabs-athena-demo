"""Pricing service: stands in for PriceLabs' Rails app.

The agent's local tools (pricing_agent/tools.py) call this over HTTPS, the
same way Athena's Python tools call Rails. Business rules live here, not in
the agent: a recommendation is clamped to guardrails, and price pushes are
recorded in an audit log the demo shows at the end.

Env: PRICING_API_TOKEN (bearer token the agent sends).
"""
import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

TOKEN = os.environ["PRICING_API_TOKEN"]
MAX_RAISE = 0.35  # guardrail: never raise more than 35% in one push

app = FastAPI(title="Pricing service (Rails stand-in)")
AUDIT: list[dict] = []


def auth(authorization: str = Header("")):
    if not secrets.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(401, "unauthorized")


class RecRequest(BaseModel):
    listing_id: str
    current_price: float = Field(gt=0)
    comp_price: float = Field(gt=0)
    pickup_ratio: float = Field(description="our on-the-books occupancy / comp occupancy for the window")
    event_lift: float = 1.0


class PricePush(BaseModel):
    listing_id: str
    new_price: float = Field(gt=0)
    reason: str


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/recommendation", dependencies=[Depends(auth)])
def recommendation(r: RecRequest):
    target = r.comp_price * min(r.event_lift, 1.6) ** 0.5
    if r.pickup_ratio > 1.15:  # filling faster than the comp set: room to move up
        target *= 1.05
    capped = min(target, r.current_price * (1 + MAX_RAISE))
    return {
        "listing_id": r.listing_id,
        "recommended_price": round(capped, 2),
        "change_pct": round((capped / r.current_price - 1) * 100, 1),
        "guardrail_applied": capped < target,
    }


@app.post("/prices", dependencies=[Depends(auth)])
def push_price(p: PricePush):
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **p.model_dump()}
    AUDIT.append(entry)
    return {"status": "applied", **entry}


@app.get("/audit", dependencies=[Depends(auth)])
def audit():
    return AUDIT


@app.post("/audit/reset", dependencies=[Depends(auth)])
def reset():
    AUDIT.clear()
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def page(token: str = ""):
    """Tiny audit view for the closing beat: /?token=..."""
    if not secrets.compare_digest(token, TOKEN):
        return HTMLResponse("<p>add ?token=</p>", status_code=401)
    rows = "".join(f"<tr><td>{a['at']}</td><td>{a['listing_id']}</td><td>${a['new_price']:.2f}</td><td>{a['reason']}</td></tr>" for a in AUDIT)
    return f"""<!doctype html><meta charset=utf-8><title>Price pushes</title>
<style>body{{font:15px system-ui;margin:2rem}}td,th{{padding:.4rem .8rem;border-bottom:1px solid #ddd;text-align:left}}</style>
<h2>Price pushes ({len(AUDIT)})</h2><table><tr><th>When</th><th>Listing</th><th>New price</th><th>Reason</th></tr>{rows}</table>"""
