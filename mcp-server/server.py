"""Listings data MCP server (Streamable HTTP) for the PriceLabs demo.

Runs on a Droplet inside the private NYC1 VPC, next to Managed Postgres.
Action Gateway reaches it over the VPC; nothing here is on the public internet.

Env:
  DATABASE_URL   read-only DSN (agent_reader role, private host)
  MCP_API_KEY    shared secret Action Gateway sends as the X-API-Key header
  PORT           default 8080
"""
import os
import secrets
from decimal import Decimal
from datetime import date

import psycopg
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

ROW_CAP = 500
DSN = os.environ["DATABASE_URL"]
# Empty = no auth. Action Gateway only allows plain-HTTP private URLs without
# auth ("private IP HTTP URL with a selected VPC and no authentication"); with
# HTTPS it can send a key. Here the cloud firewall limits port 8080 to the two
# peered VPC ranges, and the DB role is read-only.
API_KEY = os.environ.get("MCP_API_KEY", "")

# Action Gateway calls us by private IP, so the Host header is an IP, not a name.
# DNS-rebinding protection guards browser-facing local servers; this one is
# private-network only and requires an API key, so the check is off.
mcp = FastMCP("listings-db", stateless_http=True, json_response=True,
              transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


@mcp.tool()
def describe_schema() -> dict:
    """Describe the tables and columns in the listings database (customers, listings, nightly_rates, market_events)."""
    sql = """SELECT table_name, column_name, data_type FROM information_schema.columns
             WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"""
    out: dict[str, list[str]] = {}
    with psycopg.connect(DSN) as conn:
        for t, c, d in conn.execute(sql):
            out.setdefault(t, []).append(f"{c} {d}")
    return out


@mcp.tool()
def run_readonly_sql(sql: str) -> dict:
    """Run one read-only SQL query against the listings database.

    Aggregate in SQL (GROUP BY, AVG, percentiles) rather than pulling raw rows:
    results are capped at 500 rows and queries time out after 15 seconds.
    """
    with psycopg.connect(DSN) as conn:
        conn.read_only = True
        cur = conn.execute(sql)
        cols = [d.name for d in cur.description or []]
        rows = cur.fetchmany(ROW_CAP + 1)
    truncated = len(rows) > ROW_CAP
    return {
        "columns": cols,
        "rows": [[_jsonable(v) for v in r] for r in rows[:ROW_CAP]],
        "truncated": truncated,
    }


class ApiKey(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/healthz":
            return JSONResponse({"ok": True})
        if not API_KEY:  # private-network mode: VPC + firewall are the boundary
            return await call_next(request)
        # Action Gateway derives the header name itself, so accept the common forms.
        h = request.headers
        bearer = h.get("authorization", "")
        presented = [h.get("x-api-key", ""), h.get("api-key", ""), h.get("apikey", ""),
                     bearer[7:] if bearer.lower().startswith("bearer ") else bearer]
        if not any(p and secrets.compare_digest(p, API_KEY) for p in presented):
            print("401 from", request.client.host if request.client else "?",
                  "headers:", sorted(k for k in h.keys() if k not in ("host", "content-length")), flush=True)
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


app = mcp.streamable_http_app()  # serves /mcp
app.add_middleware(ApiKey)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
