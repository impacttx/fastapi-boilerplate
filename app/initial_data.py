import asyncio
from pathlib import Path
import sys

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import SQLModel, text

from app.database import async_session_maker, engine
from app.seed import seed_roles, seed_super_admin, seed_terms_and_conditions


async def cleanup_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.commit()


async def init_db():
    async with async_session_maker() as session:
        # Check if migration has been done
        # pyrefly: ignore [no-matching-overload]
        r = await session.exec(text("SELECT * FROM alembic_version"))
        if r.scalar() is None:
            logger.warning("⚠️ Skipping seed (run migration first) : Migration not done")
            return
        await seed_roles(session)
        tnc = await seed_terms_and_conditions(session)
        await seed_super_admin(session, tnc.revision)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(init_db())
