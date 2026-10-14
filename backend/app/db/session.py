import asyncio
import sys
from collections.abc import AsyncGenerator

# Psycopg 3 async on Windows requires WindowsSelectorEventLoopPolicy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Engine 1: querypilot_app database with app_rw role (full read/write access)
app_engine: AsyncEngine = create_async_engine(
    settings.app_database_url,
    pool_pre_ping=True,
    echo=False,
)

# Engine 2: sample_shop database with readonly_user role (isolated, read-only queries)
shop_engine: AsyncEngine = create_async_engine(
    settings.shop_database_url,
    pool_pre_ping=True,
    echo=False,
)

# Engine 3: sample_shop_bench with readonly_user role (isolated benchmark query runs)
bench_engine: AsyncEngine = create_async_engine(
    settings.bench_database_url,
    pool_pre_ping=True,
    echo=False,
)

# Engine 4: sample_shop_bench with postgres admin role (for index creation / cleanup ONLY)
bench_admin_engine: AsyncEngine = create_async_engine(
    settings.bench_admin_database_url,
    pool_pre_ping=True,
    echo=False,
)

# Session makers
AppAsyncSessionLocal = async_sessionmaker(
    bind=app_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

ShopAsyncSessionLocal = async_sessionmaker(
    bind=shop_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_app_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session for querypilot_app database operations."""
    async with AppAsyncSessionLocal() as session:
        yield session


async def get_shop_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session for sample_shop database operations."""
    async with ShopAsyncSessionLocal() as session:
        yield session
