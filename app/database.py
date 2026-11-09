from typing import Annotated

from fastapi import Depends
import orjson
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings import settings


def orjson_serializer(obj):
    return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NAIVE_UTC).decode()


def create_engine(dsn: str, use_ssl: bool = False) -> AsyncEngine:
    return create_async_engine(
        dsn,
        echo=False,
        future=True,
        connect_args={"ssl": {"sslmode": "require"}} if use_ssl else {},
        json_serializer=orjson_serializer,
        json_deserializer=orjson.loads,
        pool_size=20,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
    )


engine = create_engine(settings.DATABASE_URL_ASYNC, settings.POSTGRES_USE_SSL)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_async_session():
    async with async_session_maker() as session:
        yield session


class Base(AsyncAttrs, DeclarativeBase):
    __abstract__ = True
    metadata = SQLModel.metadata


SessionDep = Annotated[AsyncSession, Depends(get_async_session)]
