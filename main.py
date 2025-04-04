import logging
import json
import os
from typing import Optional

import psycopg2
import telebot
from telebot import types
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = telebot.TeleBot(os.getenv("7577933173:AAHV0TWdWbqBadzoHnpkT3mgGoYBEB49W24"))

# Подключение к PostgreSQL
conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="123",
    host="localhost",
    port="5432",
)
cur = conn.cursor()

# Загрузка задач из JSON
with open("task_data.json", "r", encoding="utf-8") as f:
    TASKS = json.load(f)

# Состояния пользователей
user_states = {}


# Клавиатура для выбора уровня сложности
def create_level_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row("Легкий", "Средний", "Сложный")
    markup.row("Баланс")
    return markup


@bot.message_handler(commands=['start'])
def start(message: types.Message):
    user = message.from_user
    cur.execute("SELECT * FROM users WHERE user_id = %s;", (user.id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users (user_id, username, balance) VALUES (%s, %s, %s);",
            (user.id, user.username, 0),
        )
        conn.commit()
        bot.send_message(
            message.chat.id,
            f"Привет, {user.first_name}! Вы успешно зарегистрированы.",
            reply_markup=create_level_keyboard(),
        )
    else:
        bot.send_message(
            message.chat.id,
            f"С возвращением, {user.first_name}!",
            reply_markup=create_level_keyboard(),
        )
    user_states[user.id] = {"state": "CHOOSING"}


@bot.message_handler(func=lambda message: message.text in ["Легкий", "Средний", "Сложный"])
def choose_level(message: types.Message):
    user_id = message.from_user.id
    level = message.text.lower()

    # Получаем случайную задачу выбранного уровня
    tasks = TASKS.get(level, [])
    if not tasks:
        bot.send_message(message.chat.id, "Задачи для этого уровня не найдены.")
        return

    task = tasks[0]  # Берем первую задачу (можно реализовать случайный выбор)

    user_states[user_id] = {
        "state": "AWAITING_ANSWER",
        "level": level,
        "current_task": task,
        "attempts": 0
    }

    bot.send_message(
        message.chat.id,
        f"Вопрос ({level} уровень):\n{task['question']}",
        reply_markup=types.ReplyKeyboardRemove()
    )


@bot.message_handler(func=lambda message: message.text == "Баланс")
def show_balance(message: types.Message):
    user = message.from_user
    cur.execute("SELECT balance FROM users WHERE user_id = %s;", (user.id,))
    balance = cur.fetchone()[0]
    bot.send_message(
        message.chat.id,
        f"Ваш текущий баланс: {balance} баллов.",
        reply_markup=create_level_keyboard()
    )


@bot.message_handler(func=lambda message: True)
def handle_answer(message: types.Message):
    user_id = message.from_user.id
    user_state = user_states.get(user_id, {})

    if user_state.get("state") != "AWAITING_ANSWER":
        return

    current_task = user_state["current_task"]
    user_answer = message.text.strip().lower()
    correct_answer = current_task["answer"].lower()

    if user_answer == correct_answer:
        reward = current_task.get("reward", 1)
        cur.execute(
            "UPDATE users SET balance = balance + %s WHERE user_id = %s;",
            (reward, user_id)
        )
        conn.commit()
        bot.send_message(
            message.chat.id,
            f"✅ Правильно! Вы получили {reward} баллов.",
            reply_markup=create_level_keyboard()
        )
        user_states[user_id] = {"state": "CHOOSING"}
    else:
        user_state["attempts"] += 1
        if user_state["attempts"] >= 3:  # Лимит попыток
            bot.send_message(
                message.chat.id,
                f"❌ Неверно. Правильный ответ: {correct_answer}",
                reply_markup=create_level_keyboard()
            )
            user_states[user_id] = {"state": "CHOOSING"}
        else:
            bot.send_message(
                message.chat.id,
                "❌ Неверно. Попробуйте еще раз."
            )


if __name__ == "__main__":
    logger.info("Бот запущен")
    bot.infinity_polling()