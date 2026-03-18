import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from src.utils.db import engine, MenuCategory, MenuItem, MenuSpecial

SPICE_NOTE = "Spice level required: No Spice / Mild / Hot / Blaze / Reaper"

CATEGORIES = [
    {"name": "Meals", "description": "All meals include fries and 1x 2oz Hot Chickz Sauce. All chicken requires a spice level: No Spice / Mild / Hot / Blaze / Reaper.", "sort_order": 1},
    {"name": "Bowls", "description": "Fries base with chopped chicken and Hot Chickz Sauce drizzle. All chicken requires a spice level: No Spice / Mild / Hot / Blaze / Reaper.", "sort_order": 2},
    {"name": "Chicken Over Rice", "description": "Yellow rice topped with chopped chicken. Served with white sauce and hot sauce. Spice level required.", "sort_order": 3},
    {"name": "Sides", "description": "Individual side items.", "sort_order": 4},
    {"name": "Party Packs", "description": "Large packs for groups. All chicken requires a spice level: No Spice / Mild / Hot / Blaze / Reaper.", "sort_order": 5},
    {"name": "Drinks", "description": "Fountain drinks and frozen lemonades.", "sort_order": 6},
    {"name": "Catering", "description": "Catering packages. Please order at least 2 hours in advance. Choose from trays: chicken over fries with sauce, sliders, or tenders.", "sort_order": 7},
]

ITEMS = {
    "Meals": [
        {
            "name": "Hot Chickz #3",
            "description": "Single Slider Meal. 1 slider served with fries. Includes pickles, coleslaw, and 1x 2oz Hot Chickz Sauce. " + SPICE_NOTE,
            "price": 7.99,
            "sort_order": 1,
        },
        {
            "name": "Hot Chickz #2",
            "description": "Double Tender Meal. 2 tenders served with fries. Includes pickles and 1x 2oz Hot Chickz Sauce. " + SPICE_NOTE,
            "price": 8.99,
            "sort_order": 2,
        },
        {
            "name": "Hot Chickz #1",
            "description": "Slider and Tender Combo. 1 slider and 1 tender served with fries. Includes pickles, coleslaw, and 1x 2oz Hot Chickz Sauce. " + SPICE_NOTE,
            "price": 9.99,
            "sort_order": 3,
        },
        {
            "name": "Hot Chickz #4",
            "description": "Double Slider Meal. 2 sliders served with fries. Includes pickles, coleslaw, and 1x 2oz Hot Chickz Sauce. " + SPICE_NOTE,
            "price": 11.99,
            "sort_order": 4,
        },
    ],
    "Bowls": [
        {
            "name": "Hot Chickz #5",
            "description": "Chicken Bowl. Chopped chicken over a fries base with Hot Chickz Sauce drizzle. " + SPICE_NOTE,
            "price": 9.99,
            "sort_order": 1,
        },
        {
            "name": "Hot Chickz #6",
            "description": "Chicken Mac Bowl. Chopped chicken and Mac n Cheese over a fries base with Hot Chickz Sauce drizzle. " + SPICE_NOTE,
            "price": 10.99,
            "sort_order": 2,
        },
        {
            "name": "Hot Chickz #7",
            "description": "Chicken Slaw Bowl. Chopped chicken and Coleslaw over a fries base with Hot Chickz Sauce drizzle. " + SPICE_NOTE,
            "price": 11.99,
            "sort_order": 3,
        },
        {
            "name": "Hot Chickz #8",
            "description": "Fully Loaded Bowl. Chopped chicken, Mac n Cheese, and Coleslaw over a fries base with Hot Chickz Sauce drizzle. " + SPICE_NOTE,
            "price": 12.99,
            "sort_order": 4,
        },
    ],
    "Chicken Over Rice": [
        {
            "name": "Chicken Over Rice",
            "description": "Yellow rice topped with chopped chicken. Served with white sauce and hot sauce. " + SPICE_NOTE,
            "price": 10.99,
            "sort_order": 1,
        },
    ],
    "Sides": [
        {"name": "Fries", "description": "Regular fries.", "price": 2.99, "sort_order": 1},
        {"name": "Cheesy Fries", "description": "Fries topped with cheese sauce.", "price": 3.99, "sort_order": 2},
        {"name": "Mac n Cheese", "description": "8oz mac and cheese.", "price": 3.99, "sort_order": 3},
        {"name": "Rice", "description": "8oz yellow rice.", "price": 2.99, "sort_order": 4},
        {"name": "Coleslaw", "description": "8oz coleslaw.", "price": 2.49, "sort_order": 5},
        {"name": "Slider", "description": "1 slider with pickles, coleslaw, and sauce.", "price": 2.99, "sort_order": 6},
        {"name": "Tender", "description": "1 tender with pickles and 1x 2oz Hot Chickz Sauce. " + SPICE_NOTE, "price": 2.99, "sort_order": 7},
        {"name": "Pickles", "description": "8oz pickles.", "price": 2.49, "sort_order": 8},
        {"name": "Cheese Sauce", "description": "8oz cheese sauce.", "price": 2.49, "sort_order": 9},
        {"name": "Hot Chickz Sauce", "description": "8oz Hot Chickz Sauce.", "price": 2.49, "sort_order": 10},
    ],
    "Party Packs": [
        {
            "name": "6 Tender Party Pack",
            "description": "6 tenders with 2 breads, pickles, and 1x 3oz Hot Chickz Sauce. " + SPICE_NOTE,
            "price": 17.99,
            "sort_order": 1,
        },
        {
            "name": "10 Tender Party Pack",
            "description": "10 tenders with 4 breads, pickles, and 1x 5oz Hot Chickz Sauce. " + SPICE_NOTE,
            "price": 27.99,
            "sort_order": 2,
        },
    ],
    "Drinks": [
        {"name": "Fountain Drink", "description": "Pepsi or Coke. Small or large.", "price": 1.99, "sort_order": 1},
        {"name": "Frozen Lemonade", "description": "Flavors: Watermelon, Blueberry, Cherry, Original, Mixed. Small or large.", "price": 2.49, "sort_order": 2},
    ],
    "Catering": [
        {
            "name": "Catering — 2 Trays + 2 Sides",
            "description": "Choose any 2 trays and 2 sides. Tray options: chicken over fries with sauce, 10 sliders with sauce, 20 tenders with bread and sauce. Available sides: Coleslaw, Fries, Mac n Cheese, Pickles, Cheese Sauce, Hot Chickz Sauce. Order at least 2 hours in advance.",
            "price": 100.00,
            "sort_order": 1,
        },
        {
            "name": "Catering — 3 Trays + 4 Sides",
            "description": "Choose any 3 trays and 4 sides. Same tray and side options as above. Order at least 2 hours in advance.",
            "price": 150.00,
            "sort_order": 2,
        },
        {
            "name": "Catering — 4 Trays + 6 Sides",
            "description": "Choose any 4 trays and 6 sides. Same tray and side options as above. Order at least 2 hours in advance.",
            "price": 200.00,
            "sort_order": 3,
        },
    ],
}


async def seed():
    async with AsyncSession(engine) as session:
        print("Clearing existing menu data...")
        await session.execute(delete(MenuItem))
        await session.execute(delete(MenuCategory))
        await session.execute(delete(MenuSpecial))
        await session.commit()

        print("Seeding categories and items...")
        for cat_data in CATEGORIES:
            category = MenuCategory(
                name=cat_data["name"],
                description=cat_data["description"],
                sort_order=cat_data["sort_order"],
                is_available=True,
            )
            session.add(category)
            await session.flush()

            items = ITEMS.get(cat_data["name"], [])
            for item_data in items:
                item = MenuItem(
                    category_id=category.id,
                    name=item_data["name"],
                    description=item_data["description"],
                    price=item_data["price"],
                    is_available=True,
                    sort_order=item_data["sort_order"],
                )
                session.add(item)

        await session.commit()
        total_items = sum(len(v) for v in ITEMS.values())
        print(f"Done! Seeded {len(CATEGORIES)} categories and {total_items} items.")


if __name__ == "__main__":
    asyncio.run(seed())
