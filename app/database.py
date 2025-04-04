from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:123@localhost/postgres"

async_engine = create_async_engine(DATABASE_URL, echo=True)
Base = declarative_base()
async_session_maker = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)