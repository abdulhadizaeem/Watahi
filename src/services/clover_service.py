import os

import httpx


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('CLOVER_API_TOKEN', '')}",
        "Content-Type": "application/json",
    }


def _base() -> str:
    merchant_id = os.getenv("CLOVER_MERCHANT_ID", "")
    base = os.getenv("CLOVER_BASE_URL", "https://api.clover.com/v3")
    return f"{base}/merchants/{merchant_id}"


async def get_clover_order_types() -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{_base()}/order_types", headers=_headers())
        r.raise_for_status()
        return r.json().get("elements", [])


async def get_clover_inventory() -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_base()}/items",
            headers=_headers(),
            params={"expand": "categories", "limit": 500},
        )
        r.raise_for_status()
        return r.json().get("elements", [])


async def create_clover_order(
    order_type_id: str | None,
    customer_name: str,
    order_type: str,
    special_notes: str = "",
    delivery_address: str = "",
) -> str:
    note_parts = [order_type.upper(), customer_name]
    if special_notes:
        note_parts.append(special_notes)
    if delivery_address and order_type == "delivery":
        note_parts.append(f"Deliver to: {delivery_address}")
    note = " | ".join(filter(None, note_parts))

    payload: dict = {"note": note}
    if order_type_id:
        payload["orderType"] = {"id": order_type_id}

    async with httpx.AsyncClient() as client:
        r = await client.post(f"{_base()}/orders", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()["id"]


async def add_line_item(clover_order_id: str, clover_item_id: str, special_instructions: str = "") -> dict:
    payload: dict = {"item": {"id": clover_item_id}}
    if special_instructions:
        payload["note"] = special_instructions
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_base()}/orders/{clover_order_id}/line_items",
            headers=_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


async def print_order_to_kitchen(clover_order_id: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_base()}/orders/{clover_order_id}/print_event",
            headers=_headers(),
        )
        return r.status_code in (200, 201, 204)


async def push_order_to_clover(
    order_items: list[dict],
    order_type: str,
    customer_name: str,
    delivery_address: str = "",
    special_notes: str = "",
    item_id_map: dict | None = None,
) -> dict:
    if item_id_map is None:
        item_id_map = {}

    order_type_map = {
        "pickup": os.getenv("CLOVER_PICKUP_TYPE_ID", ""),
        "delivery": os.getenv("CLOVER_DELIVERY_TYPE_ID", ""),
        "dine_in": os.getenv("CLOVER_DINEIN_TYPE_ID", ""),
    }
    order_type_id = order_type_map.get(order_type) or None

    clover_order_id = await create_clover_order(
        order_type_id=order_type_id,
        customer_name=customer_name,
        order_type=order_type,
        special_notes=special_notes,
        delivery_address=delivery_address,
    )

    skipped_items = []
    for item in order_items:
        item_name = item.get("item", "")
        quantity = int(item.get("quantity", 1))
        instructions = item.get("special_instructions", "")
        clover_item_id = item_id_map.get(item_name)
        if not clover_item_id:
            skipped_items.append(item_name)
            continue
        for _ in range(quantity):
            await add_line_item(clover_order_id, clover_item_id, instructions)

    await print_order_to_kitchen(clover_order_id)
    return {"clover_order_id": clover_order_id, "skipped_items": skipped_items}
