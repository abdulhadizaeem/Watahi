import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from src.utils.db import engine

async def alter_db():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE agent_settings ADD COLUMN restaurant_info VARCHAR DEFAULT 'We are open daily from 11am to 10pm.'"))
        except Exception as e:
            pass
        try:
            await conn.execute(text("ALTER TABLE agent_settings ADD COLUMN wait_time_pickup VARCHAR DEFAULT '15'"))
        except Exception as e:
            pass
        try:
            await conn.execute(text("ALTER TABLE agent_settings ADD COLUMN wait_time_delivery VARCHAR DEFAULT '30'"))
        except Exception as e:
            pass
        print("DB alterations complete.")

if __name__ == "__main__":
    asyncio.run(alter_db())
