# crud.py
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, Task

# Users
async def get_or_create_user(user_id: int, session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        user = User(id=user_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user

async def update_balance(user_id: int, amount: int, session: AsyncSession):
    user = await get_or_create_user(user_id, session)
    user.balance += amount
    await session.commit()

# Tasks
async def get_random_task(level: str, session: AsyncSession) -> Task | None:
    result = await session.execute(
        select(Task).where(Task.level == level).order_by(func.random()).limit(1)
    )
    return result.scalar_one_or_none()
