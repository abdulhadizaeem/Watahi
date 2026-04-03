import logging
import os

import httpx

_logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('CLOVER_API_TOKEN', '')}",
        "Content-Type": "application/json",
    }


def _merchant_base() -> str:
    merchant_id = os.getenv("CLOVER_MERCHANT_ID", "")
    base = os.getenv("CLOVER_BASE_URL", "https://api.clover.com/v3")
    return f"{base}/merchants/{merchant_id}"


async def push_order_to_clover(
    order_items: list[dict],
    customer_name: str,
    order_type_id: str | None = None,
) -> dict:
    order_type_id = order_type_id or os.getenv("CLOVER_ORDER_TYPE_ID", "")

    line_items = []
    for item in order_items:
        name = item.get("item", "Unknown Item")
        quantity = int(item.get("quantity", 1))
        price_dollars = float(item.get("price", 0))
        note = item.get("special_instructions", "")
        entry: dict = {
            "name": name,
            "price": int(price_dollars * 100),
            "unitQty": 1000 * quantity,
        }
        if note:
            entry["note"] = note
        line_items.append(entry)

    payload: dict = {
        "orderCart": {
            "title": "Vaxis",
            "state": "open",
            "lineItems": line_items,
        }
    }
    if order_type_id:
        payload["orderCart"]["orderType"] = {"id": order_type_id}

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{_merchant_base()}/atomic_order/orders",
            headers=_headers(),
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        order_id = data.get("id") or data.get("href", "").split("/")[-1]
        _logger.info("Clover order created: %s", order_id)

        if order_id:
            try:
                print_resp = await client.post(
                    f"{_merchant_base()}/print_event",
                    headers=_headers(),
                    json={"orderRef": {"id": order_id}},
                )
                _logger.info("Print event: %s %s", print_resp.status_code, print_resp.text[:100])
            except Exception as exc:
                _logger.error("Print event failed for order %s: %s", order_id, exc)

        return {"clover_order_id": order_id}


async def get_clover_inventory() -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{_merchant_base()}/items",
            headers=_headers(),
            params={"expand": "categories", "limit": 500},
        )
        r.raise_for_status()
        return r.json().get("elements", [])


async def get_clover_order_types() -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_merchant_base()}/order_types", headers=_headers())
        r.raise_for_status()
        return r.json().get("elements", [])


async def fetch_clover_item(item_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{_merchant_base()}/items/{item_id}",
            headers=_headers(),
            params={"expand": "categories"},
        )
        r.raise_for_status()
        return r.json()


async def fetch_all_clover_items() -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_merchant_base()}/items",
            headers=_headers(),
            params={"expand": "categories", "limit": 500},
        )
        r.raise_for_status()
        return r.json().get("elements", [])
