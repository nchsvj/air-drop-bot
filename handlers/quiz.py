# handlers/quiz.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from app.database.db import async_session
from app.database.crud import get_or_create_user, update_balance, get_random_task

router = Router()

class QuizState(StatesGroup):
    waiting_for_answer = State()

@router.callback_query(F.data == "choose_difficulty")
async def choose_difficulty(call: CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Лёгкий", callback_data="level_easy"),
            InlineKeyboardButton(text="Нормальный", callback_data="level_normal"),
            InlineKeyboardButton(text="Сложный", callback_data="level_hard")
        ]
    ])
    await call.message.answer("Выберите уровень сложности:", reply_markup=markup)

@router.callback_query(F.data == "check_balance")
async def check_balance(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(call.from_user.id, session)
        await call.message.answer(f"💰 Ваш баланс: {user.balance} Обезьянка-койнов")

@router.callback_query(F.data.startswith("level_"))
async def send_task(call: CallbackQuery, state: FSMContext):
    level = call.data.split("_")[1]

    async with async_session() as session:
        task = await get_random_task(level, session)

    if not task:
        await call.message.answer("❗ Нет заданий для этого уровня.")
        return

    await state.set_state(QuizState.waiting_for_answer)
    await state.update_data(task_id=task.id, correct_answer=task.answer, reward=task.reward)

    await call.message.answer(f"🔍 Задание: {task.question}\n✏️ Напишите ответ в чат.")

@router.message(QuizState.waiting_for_answer)
async def handle_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    correct_answer = data.get("correct_answer")
    reward = data.get("reward")

    if not correct_answer:
        await message.answer("❗ Ошибка. Попробуйте снова.")
        await state.clear()
        return

    if message.text.strip().lower() == correct_answer.lower():
        async with async_session() as session:
            await update_balance(message.from_user.id, reward, session)

        await message.answer(f"✅ Верно! Вы получили {reward} Обезьянка-койнов.")
    else:
        await message.answer("❌ Неправильно. Попробуйте снова или выберите новое задание.")

    await state.clear()
