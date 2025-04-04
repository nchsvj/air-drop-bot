# scripts/import_tasks.py
import json
import asyncio

from app.database.db import async_session
from app.database.models import Task

TASKS_FILE = "task_data.json"  # убедись, что файл рядом

async def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    async with async_session() as session:
        for level, tasks in data.items():
            for task in tasks:
                t = Task(level=level, question=task["question"], answer=task["answer"], reward=task.get("reward", 1))
                session.add(t)
        await session.commit()
    print("✅ Задания успешно импортированы в базу данных!")

if __name__ == "__main__":
    asyncio.run(load_tasks())
