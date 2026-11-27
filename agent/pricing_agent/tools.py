"""Local tools: plain Python functions that ship with the agent.

They run inside the Harness Runtime sandbox and call the pricing service
(the stand-in for PriceLabs' Rails app) over HTTPS. Business rules live in
that service; these are thin wrappers, like Athena's Rails-backed tools.
"""
import os

import httpx

_BASE = os.environ.get("PRICING_API_URL", "").rstrip("/")


def _post(path: str, body: dict) -> dict:
    r = httpx.post(f"{_BASE}{path}", json=body, timeout=20,
                   headers={"Authorization": f"Bearer {os.environ['PRICING_API_TOKEN']}"})
    r.raise_for_status()
    return r.json()


def get_price_recommendation(listing_id: str, current_price: float, comp_price: float,
                             pickup_ratio: float, event_lift: float = 1.0) -> dict:
    """Ask the pricing service for a recommended nightly price for one listing.

    Args:
        listing_id: e.g. CS-00042
        current_price: the listing's current average nightly price for the window
        comp_price: the comp set's average nightly price for the window
        pickup_ratio: our on-the-books occupancy divided by comp-set occupancy for the window
        event_lift: expected demand multiplier from market events in the window (1.0 if none)
    """
    return _post("/recommendation", locals())


def apply_price_change(listing_id: str, new_price: float, reason: str) -> dict:
    """Push a new nightly base price for a listing to the pricing service. Use only for listings you have a recommendation for.

    Args:
        listing_id: e.g. CS-00042
        new_price: the recommended price returned by get_price_recommendation
        reason: one short sentence explaining the change
    """
    return _post("/prices", locals())


LOCAL_TOOLS = [get_price_recommendation, apply_price_change]
