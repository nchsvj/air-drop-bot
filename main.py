import logging
import json
import os
import random
from typing import Dict, Any, Optional

import psycopg2
from telebot import TeleBot, types
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
bot = TeleBot(os.getenv("TELEGRAM_TOKEN"))


# Подключение к PostgreSQL
def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "123"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        raise


conn = get_db_connection()
cur = conn.cursor()


# Инициализация базы данных
def init_db():
    try:
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        conn.rollback()


init_db()


# Загрузка задач
def load_tasks():
    try:
        with open("task_data.json", "r", encoding="utf-8") as f:
            tasks = json.load(f)

            # Проверка структуры данных
            for level in ["легкий", "средний", "сложный"]:
                if level not in tasks:
                    tasks[level] = []
                for task in tasks[level]:
                    if "question" not in task or "answer" not in task:
                        logger.warning(f"Некорректная задача в уровне {level}")

            return tasks
    except FileNotFoundError:
        logger.error("Файл task_data.json не найден")
        return {"легкий": [], "средний": [], "сложный": []}
    except json.JSONDecodeError:
        logger.error("Ошибка при чтении task_data.json")
        return {"легкий": [], "средний": [], "сложный": []}


TASKS = load_tasks()

# Состояния пользователей
user_states: Dict[int, Dict[str, Any]] = {}


# Клавиатуры
def create_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Легкий", "Средний", "Сложный")
    markup.row("Баланс", "Статистика", "Помощь")
    return markup


def create_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Отмена")
    return markup


# Команда /start
@bot.message_handler(commands=['start'])
def start(message: types.Message):
    user = message.from_user
    try:
        cur.execute("SELECT * FROM users WHERE user_id = %s;", (user.id,))
        if cur.fetchone() is None:
            cur.execute(
                """INSERT INTO users 
                (user_id, username, first_name, last_name, balance) 
                VALUES (%s, %s, %s, %s, %s);""",
                (user.id, user.username, user.first_name, user.last_name, 0),
            )
            conn.commit()
            bot.send_message(
                message.chat.id,
                f"Привет, {user.first_name}! Вы успешно зарегистрированы.",
                reply_markup=create_main_keyboard(),
            )
        else:
            bot.send_message(
                message.chat.id,
                f"С возвращением, {user.first_name}!",
                reply_markup=create_main_keyboard(),
            )
        user_states[user.id] = {"state": "MAIN_MENU"}
    except psycopg2.Error as e:
        logger.error(f"Ошибка БД: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")


# Выбор уровня сложности
@bot.message_handler(func=lambda message: message.text in ["Легкий", "Средний", "Сложный"])
def choose_level(message: types.Message):
    user_id = message.from_user.id
    level = message.text.lower()

    tasks = TASKS.get(level, [])
    if not tasks:
        bot.send_message(message.chat.id, "Задачи для этого уровня не найдены.")
        return

    # Выбираем случайную задачу
    task = random.choice(tasks)

    user_states[user_id] = {
        "state": "AWAITING_ANSWER",
        "level": level,
        "current_task": task,
        "attempts": 0
    }

    bot.send_message(
        message.chat.id,
        f"Вопрос ({level} уровень):\n{task['question']}",
        reply_markup=create_cancel_keyboard()
    )


# Обработка ответа
@bot.message_handler(func=lambda message: True)
def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_state = user_states.get(user_id, {})

    if message.text == "Отмена":
        user_states[user_id] = {"state": "MAIN_MENU"}
        bot.send_message(
            message.chat.id,
            "Возвращаемся в главное меню.",
            reply_markup=create_main_keyboard()
        )
        return

    if message.text == "Баланс":
        show_balance(message)
        return

    if message.text == "Статистика":
        show_stats(message)
        return

    if message.text == "Помощь":
        show_help(message)
        return

    if user_state.get("state") == "AWAITING_ANSWER":
        process_answer(message, user_state)
    else:
        bot.send_message(
            message.chat.id,
            "Выберите действие из меню.",
            reply_markup=create_main_keyboard()
        )


def process_answer(message: types.Message, user_state: Dict[str, Any]):
    user_id = message.from_user.id
    current_task = user_state["current_task"]
    user_answer = message.text.strip().lower()
    correct_answer = current_task["answer"].lower()
    level = user_state["level"]

    try:
        if user_answer == correct_answer:
            reward = current_task.get("reward", 1)

            # Обновляем статистику пользователя
            cur.execute("""
                UPDATE users 
                SET balance = balance + %s,
                    correct_answers = correct_answers + 1,
                    total_questions = total_questions + 1
                WHERE user_id = %s;
            """, (reward, user_id))

            # Записываем ответ
            cur.execute("""
                INSERT INTO user_answers 
                (user_id, question, answer, is_correct, level)
                VALUES (%s, %s, %s, %s, %s);
            """, (user_id, current_task["question"], user_answer, True, level))

            conn.commit()

            bot.send_message(
                message.chat.id,
                f"✅ Правильно! Вы получили {reward} баллов.",
                reply_markup=create_main_keyboard()
            )
        else:
            user_state["attempts"] += 1

            # Записываем неправильный ответ
            cur.execute("""
                INSERT INTO user_answers 
                (user_id, question, answer, is_correct, level)
                VALUES (%s, %s, %s, %s, %s);
            """, (user_id, current_task["question"], user_answer, False, level))

            cur.execute("""
                UPDATE users SET total_questions = total_questions + 1
                WHERE user_id = %s;
            """, (user_id,))

            conn.commit()

            if user_state["attempts"] >= 1:
                bot.send_message(
                    message.chat.id,
                    f"❌ Неверно.",
                    reply_markup=create_main_keyboard()
                )
                user_states[user_id] = {"state": "MAIN_MENU"}

        user_states[user_id] = {"state": "MAIN_MENU"}
    except psycopg2.Error as e:
        logger.error(f"Ошибка БД: {e}")
        conn.rollback()
        bot.send_message(
            message.chat.id,
            "Произошла ошибка при обработке ответа.",
            reply_markup=create_main_keyboard()
        )
        user_states[user_id] = {"state": "MAIN_MENU"}


def show_balance(message: types.Message):
    user_id = message.from_user.id
    try:
        cur.execute("""
            SELECT balance, correct_answers, total_questions 
            FROM users WHERE user_id = %s;
        """, (user_id,))
        result = cur.fetchone()

        if result:
            balance, correct, total = result
            accuracy = (correct / total * 100) if total > 0 else 0

            bot.send_message(
                message.chat.id,
                f"💰 Баланс: {balance} баллов\n"
                f"✅ Правильных ответов: {correct}\n"
                f"📊 Всего вопросов: {total}\n"
                f"🎯 Точность: {accuracy:.1f}%",
                reply_markup=create_main_keyboard()
            )
        else:
            bot.send_message(
                message.chat.id,
                "Пользователь не найден. Нажмите /start",
                reply_markup=create_main_keyboard()
            )
    except psycopg2.Error as e:
        logger.error(f"Ошибка БД: {e}")
        bot.send_message(
            message.chat.id,
            "Не удалось получить информацию о балансе.",
            reply_markup=create_main_keyboard()
        )


def show_stats(message: types.Message):
    user_id = message.from_user.id
    try:
        # Общая статистика
        cur.execute("""
            SELECT 
                COUNT(*) as total_answers,
                SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct_answers,
                level
            FROM user_answers
            WHERE user_id = %s
            GROUP BY level;
        """, (user_id,))

        stats = cur.fetchall()

        if not stats:
            bot.send_message(
                message.chat.id,
                "У вас пока нет статистики. Ответьте на несколько вопросов!",
                reply_markup=create_main_keyboard()
            )
            return

        message_text = "📊 Ваша статистика:\n\n"
        for row in stats:
            total, correct, level = row
            accuracy = (correct / total * 100) if total > 0 else 0
            message_text += (
                f"🏆 {level.capitalize()} уровень:\n"
                f"✅ {correct} из {total}\n"
                f"🎯 Точность: {accuracy:.1f}%\n\n"
            )

        bot.send_message(
            message.chat.id,
            message_text,
            reply_markup=create_main_keyboard()
        )
    except psycopg2.Error as e:
        logger.error(f"Ошибка БД: {e}")
        bot.send_message(
            message.chat.id,
            "Не удалось получить статистику.",
            reply_markup=create_main_keyboard()
        )


def show_help(message: types.Message):
    help_text = (
        "ℹ️ Помощь по боту:\n\n"
        "Выберите уровень сложности вопроса:\n"
        "• Легкий - простые вопросы (1 балл)\n"
        "• Средний - вопросы средней сложности (2 балла)\n"
        "• Сложный - сложные вопросы (3 балла)\n\n"
        "Другие команды:\n"
        "• Баланс - показать ваш текущий баланс\n"
        "• Статистика - показать вашу статистику\n"
        "• Отмена - вернуться в главное меню\n\n"
        "Для начала работы нажмите /start"
    )

    bot.send_message(
        message.chat.id,
        help_text,
        reply_markup=create_main_keyboard()
    )


if __name__ == "__main__":
    try:
        logger.info("Бот запущен")
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Ошибка в работе бота: {e}")
    finally:
        cur.close()
        conn.close()
        logger.info("Бот остановлен")