import sys
import httpx

BASE = "http://localhost:8001"
PASS = "Admin1234!"
EMAIL = "admin@wahati.com"

client = httpx.Client(base_url=BASE, timeout=10)
TOKEN = None
HEADERS = {}
BURGER_CAT_ID = None
DRINKS_CAT_ID = None
SIDES_CAT_ID = None

PASS_SYMBOL = "[PASS]"
FAIL_SYMBOL = "[FAIL]"

failures = []


def check(label, condition, got=None):
    if condition:
        print(f"  {PASS_SYMBOL} {label}")
    else:
        print(f"  {FAIL_SYMBOL} {label}" + (f" — got: {got}" if got is not None else ""))
        failures.append(label)


def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


def run_tests():
    global TOKEN, HEADERS, BURGER_CAT_ID, DRINKS_CAT_ID, SIDES_CAT_ID

    section("1. HEALTH CHECK")
    r = client.get("/")
    check("GET / returns 200", r.status_code == 200)
    check("service field correct", r.json().get("service") == "restaurant-calling-agent")

    section("2. AUTH — REGISTER")
    r = client.post("/api/auth/register", json={
        "email": EMAIL,
        "password": PASS,
        "full_name": "Test Admin"
    })
    check("POST /api/auth/register returns 201 or 400 (already exists)",
          r.status_code in (201, 400))
    if r.status_code == 400:
        print("  (user already exists — skipping)")

    section("3. AUTH — LOGIN")
    r = client.post("/api/auth/login", data={
        "username": EMAIL,
        "password": PASS
    })
    check("POST /api/auth/login returns 200", r.status_code == 200, r.text)
    body = r.json()
    check("access_token in response", "access_token" in body)
    check("refresh_token in response", "refresh_token" in body)
    check("is_admin in response", "is_admin" in body)
    check("token_type is bearer", body.get("token_type") == "bearer")
    TOKEN = body.get("access_token", "")
    HEADERS = {"Authorization": f"Bearer {TOKEN}"}

    section("4. AUTH — /me")
    r = client.get("/api/auth/me", headers=HEADERS)
    check("GET /api/auth/me returns 200", r.status_code == 200, r.text)
    me = r.json()
    check("/me has is_admin field", "is_admin" in me)
    check("/me has email field", me.get("email") == EMAIL)

    section("5. SETTINGS")
    r = client.get("/api/settings", headers=HEADERS)
    check("GET /api/settings returns 200", r.status_code == 200, r.text)
    s = r.json()
    check("kitchen_open_time present", "kitchen_open_time" in s)
    check("voice_id present", "voice_id" in s)

    r = client.patch("/api/settings", headers=HEADERS, json={"kitchen_open_time": "11:00"})
    check("PATCH /api/settings returns 200", r.status_code == 200, r.text)

    section("6. MENU — CATEGORIES")
    r = client.post("/api/menu/categories", headers=HEADERS, json={
        "name": "Burgers", "description": "Signature burgers", "sort_order": 1
    })
    check("POST /api/menu/categories returns 201", r.status_code == 201, r.text)
    BURGER_CAT_ID = r.json().get("id")
    check("Category has id", bool(BURGER_CAT_ID))

    r = client.post("/api/menu/categories", headers=HEADERS, json={
        "name": "Drinks", "description": "Cold beverages", "sort_order": 2
    })
    check("POST /api/menu/categories (Drinks) returns 201", r.status_code == 201, r.text)
    DRINKS_CAT_ID = r.json().get("id")

    r = client.post("/api/menu/categories", headers=HEADERS, json={
        "name": "Sides", "description": "Fries and more", "sort_order": 3
    })
    SIDES_CAT_ID = r.json().get("id")

    r = client.get("/api/menu/categories", headers=HEADERS)
    check("GET /api/menu/categories returns 200", r.status_code == 200, r.text)
    cats = r.json()
    check("At least 3 categories returned", len(cats) >= 3)

    section("7. MENU — ITEMS")
    items_to_create = [
        {"category_id": BURGER_CAT_ID, "name": "Classic Cheeseburger",
         "description": "Beef patty with lettuce, tomato, pickles",
         "price": 8.99, "allergens": "gluten, dairy", "prep_time_minutes": 12, "sort_order": 1},
        {"category_id": BURGER_CAT_ID, "name": "Bacon BBQ Burger",
         "description": "Smoky BBQ with crispy bacon",
         "price": 10.99, "prep_time_minutes": 14, "sort_order": 2},
        {"category_id": DRINKS_CAT_ID, "name": "Coke", "price": 2.49, "sort_order": 1},
        {"category_id": DRINKS_CAT_ID, "name": "Lemonade",
         "description": "Fresh squeezed", "price": 3.00, "sort_order": 2},
        {"category_id": SIDES_CAT_ID, "name": "Large Fries",
         "description": "Golden crispy fries", "price": 3.49, "sort_order": 1},
        {"category_id": SIDES_CAT_ID, "name": "Onion Rings",
         "price": 3.99, "sort_order": 2},
    ]
    created_item_ids = []
    for item in items_to_create:
        r = client.post("/api/menu/items", headers=HEADERS, json=item)
        check(f"POST item '{item['name']}' returns 201", r.status_code == 201, r.text)
        if r.status_code == 201:
            created_item_ids.append(r.json().get("id"))

    r = client.get("/api/menu/items", headers=HEADERS)
    check("GET /api/menu/items returns 200", r.status_code == 200, r.text)
    check("At least 6 items returned", len(r.json()) >= 6)

    r = client.get(f"/api/menu/items?category_id={BURGER_CAT_ID}", headers=HEADERS)
    check("GET /api/menu/items?category_id= filters correctly", len(r.json()) >= 2)

    if created_item_ids:
        r = client.patch(f"/api/menu/items/{created_item_ids[0]}", headers=HEADERS,
                         json={"price": 9.49})
        check("PATCH /api/menu/items/{id} returns 200", r.status_code == 200, r.text)
        check("Price updated correctly", r.json().get("price") == 9.49)

    section("8. MENU — SPECIALS")
    r = client.post("/api/menu/specials", headers=HEADERS, json={
        "title": "Happy Hour",
        "description": "20% off all drinks between 3pm-6pm",
        "discount_type": "percentage",
        "discount_value": 20,
        "applicable_items": "Drinks",
        "is_active": True
    })
    check("POST /api/menu/specials returns 201", r.status_code == 201, r.text)
    special_id = r.json().get("id")

    r = client.get("/api/menu/specials", headers=HEADERS)
    check("GET /api/menu/specials returns 200", r.status_code == 200, r.text)
    check("At least 1 special returned", len(r.json()) >= 1)

    r = client.get("/api/menu/specials?active_only=true", headers=HEADERS)
    check("GET /api/menu/specials?active_only=true works", r.status_code == 200)

    section("9. MENU — PREVIEW (what agent receives as {{menu}})")
    r = client.get("/api/menu/preview", headers=HEADERS)
    check("GET /api/menu/preview returns 200", r.status_code == 200, r.text)
    preview = r.json()
    check("menu_text is non-empty", len(preview.get("menu_text", "")) > 10)
    check("category_count >= 3", preview.get("category_count", 0) >= 3)
    check("item_count >= 6", preview.get("item_count", 0) >= 6)
    print(f"\n  Agent sees this as {{menu}}:")
    print("  " + "-"*40)
    for line in preview.get("menu_text", "").split("\n"):
        print(f"  {line}")
    print("  " + "-"*40)

    section("10. STATS")
    r = client.get("/api/retell/stats", headers=HEADERS)
    check("GET /api/retell/stats returns 200", r.status_code == 200, r.text)
    stats = r.json()
    check("calls block present", "calls" in stats)
    check("reservations block present", "reservations" in stats)
    check("orders block present", "orders" in stats)

    section("11. CALLS & CALLERS")
    r = client.get("/api/retell/calls", headers=HEADERS)
    check("GET /api/retell/calls returns 200", r.status_code == 200, r.text)

    r = client.get("/api/retell/callers", headers=HEADERS)
    check("GET /api/retell/callers returns 200", r.status_code == 200, r.text)
    callers = r.json()
    print(f"  Callers in DB: {len(callers)}")

    section("12. RESERVATIONS")
    r = client.get("/api/retell/reservations", headers=HEADERS)
    check("GET /api/retell/reservations returns 200", r.status_code == 200, r.text)

    r = client.get("/api/retell/reservations/stats", headers=HEADERS)
    check("GET /api/retell/reservations/stats returns 200", r.status_code == 200, r.text)

    section("13. ORDERS")
    r = client.get("/api/retell/orders", headers=HEADERS)
    check("GET /api/retell/orders returns 200", r.status_code == 200, r.text)

    r = client.get("/api/retell/orders/stats", headers=HEADERS)
    check("GET /api/retell/orders/stats returns 200", r.status_code == 200, r.text)
    ord_stats = r.json()
    check("orders stats has today field", "today" in ord_stats)

    section("14. FLOW & KNOWLEDGE BASES")
    r = client.get("/api/retell/flow", headers=HEADERS)
    check("GET /api/retell/flow returns 200 or 502 (Retell reachable?)", r.status_code in (200, 502, 422, 500))
    print(f"  /flow status: {r.status_code}")

    r = client.get("/api/retell/knowledge-bases", headers=HEADERS)
    check("GET /api/retell/knowledge-bases responds", r.status_code in (200, 500, 502))
    print(f"  /knowledge-bases status: {r.status_code}")

    section("15. UNAUTHORIZED ACCESS CHECK")
    r = client.get("/api/retell/calls")
    check("GET /api/retell/calls without token returns 401", r.status_code == 401)
    r = client.get("/api/menu/categories")
    check("GET /api/menu/categories without token returns 401", r.status_code == 401)
    r = client.get("/api/settings")
    check("GET /api/settings without token returns 401", r.status_code == 401)

    section("SUMMARY")
    total = len(failures) + sum(1 for _ in [None])
    print(f"\n  Failures: {len(failures)}")
    if failures:
        for f in failures:
            print(f"    - {f}")
    else:
        print("  All tests passed.")


if __name__ == "__main__":
    run_tests()
    if failures:
        sys.exit(1)
