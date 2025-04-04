# handlers/start.py

from aiogram import Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="На чём я написан?", url="https://docs.aiogram.dev/")],
        [
            InlineKeyboardButton(text="Выбор сложности", callback_data="choose_difficulty"),
            InlineKeyboardButton(text="Баланс", callback_data="check_balance")
        ]
    ])

    await message.answer(
        "👋 Привет! Здесь ты можешь зарабатывать крипту, выполняя задания!",
        reply_markup=markup
    )
