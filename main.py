import logging
import json
import os
import random
from typing import Dict, Any, Optional
from datetime import datetime, time, timedelta
import schedule
import threading
import time as time_module

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
            password=os.getenv("DB_PASSWORD", "kali1122"),
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
        # Создаем таблицу для расписания airdrop
        cur.execute("""
            CREATE TABLE IF NOT EXISTS airdrop_schedule (
                id SERIAL PRIMARY KEY,
                scheduled_time TIME NOT NULL
            );
        """)

        # Добавляем стандартное время для airdrop, если его нет
        cur.execute("""
            INSERT INTO airdrop_schedule (scheduled_time) 
            VALUES ('10:00:00'), ('15:00:00'), ('20:00:00')
            ON CONFLICT DO NOTHING;
        """)
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
    markup.row("Баланс", "Статистика", "Помощь")
    markup.row("Claim Airdrop")
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
                f"Привет, {user.first_name}! Вы успешно зарегистрированы. "
                f"Теперь вы будете получать ежедневные airdrop с вопросами разной сложности. "
                f"Используйте команду /claim чтобы получить вопрос, когда придет уведомление.",
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


# Команда /claim для получения airdrop
@bot.message_handler(commands=['claim'])
@bot.message_handler(func=lambda message: message.text.lower() == "claim airdrop")
def claim_airdrop(message: types.Message):
    user_id = message.from_user.id
    try:
        cur.execute("""
            SELECT pending_airdrop_level, pending_airdrop_question 
            FROM users 
            WHERE user_id = %s;
        """, (user_id,))
        result = cur.fetchone()

        if not result or not result[0]:
            bot.send_message(
                message.chat.id,
                "У вас нет доступных airdrop. Ожидайте следующего уведомления.",
                reply_markup=create_main_keyboard()
            )
            return

        level, question_text = result
        tasks = TASKS.get(level, [])
        task = None

        # Находим задачу по тексту вопроса
        for t in tasks:
            if t["question"] == question_text:
                task = t
                break

        if not task:
            bot.send_message(
                message.chat.id,
                "Произошла ошибка при получении вопроса. Ожидайте следующего airdrop.",
                reply_markup=create_main_keyboard()
            )
            return

        user_states[user_id] = {
            "state": "AWAITING_AIRDROP_ANSWER",
            "level": level,
            "current_task": task,
            "attempts": 0
        }

        # Очищаем pending airdrop
        cur.execute("""
            UPDATE users 
            SET pending_airdrop_level = NULL, 
                pending_airdrop_question = NULL 
            WHERE user_id = %s;
        """, (user_id,))
        conn.commit()

        bot.send_message(
            message.chat.id,
            f"🎁 Airdrop вопрос ({level} уровень):\n{task['question']}",
            reply_markup=types.ForceReply(selective=False)
        )

    except psycopg2.Error as e:
        logger.error(f"Ошибка БД: {e}")
        bot.send_message(
            message.chat.id,
            "Произошла ошибка при обработке запроса.",
            reply_markup=create_main_keyboard()
        )


# Обработка ответа на airdrop вопрос
def process_airdrop_answer(message: types.Message, user_state: Dict[str, Any]):
    user_id = message.from_user.id
    current_task = user_state["current_task"]
    user_answer = message.text.strip().lower()
    correct_answer = current_task["answer"].lower()
    level = user_state["level"]
    reward = current_task.get("reward", 1)

    try:
        if user_answer == correct_answer:
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
                f"✅ Правильно! Вы получили {reward} баллов за airdrop.",
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

            bot.send_message(
                message.chat.id,
                f"❌ Неверно. Попробуйте получить новый airdrop позже.",
                reply_markup=create_main_keyboard()
            )

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


# Обработка сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_state = user_states.get(user_id, {})

    if message.text == "Баланс":
        show_balance(message)
        return

    if message.text == "Статистика":
        show_stats(message)
        return

    if message.text == "Помощь":
        show_help(message)
        return

    if user_state.get("state") == "AWAITING_AIRDROP_ANSWER":
        process_airdrop_answer(message, user_state)
    else:
        bot.send_message(
            message.chat.id,
            "Выберите действие из меню.",
            reply_markup=create_main_keyboard()
        )


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
        "Команды:\n"
        "• Баланс - показать ваш текущий баланс\n"
        "• Статистика - показать вашу статистику\n"
        "Для начала работы нажмите /start"
    )

    bot.send_message(
        message.chat.id,
        help_text,
        reply_markup=create_main_keyboard()
    )

# Система airdrop
def send_airdrop_to_users():
    try:
        # Получаем всех активных пользователей
        cur.execute("SELECT user_id FROM users;")
        users = cur.fetchall()

        if not users:
            return

        # Выбираем случайный уровень сложности
        level = random.choice(["легкий", "средний", "сложный"])
        tasks = TASKS.get(level, [])

        if not tasks:
            return

        # Выбираем случайную задачу
        task = random.choice(tasks)

        # Отправляем airdrop выбранным пользователям
        for user in users:
            user_id = user[0]

            # Проверяем, когда был последний airdrop
            cur.execute("""
                SELECT last_airdrop FROM users WHERE user_id = %s;
            """, (user_id,))
            last_airdrop = cur.fetchone()[0]

            # Если сегодня уже был airdrop, пропускаем
            if last_airdrop and last_airdrop.date() == datetime.now().date():
                continue

            # Сохраняем airdrop для пользователя
            cur.execute("""
                UPDATE users 
                SET pending_airdrop_level = %s,
                    pending_airdrop_question = %s,
                    last_airdrop = CURRENT_TIMESTAMP
                WHERE user_id = %s;
            """, (level, task["question"], user_id))

            try:
                bot.send_message(
                    user_id,
                    f"🎉 Вам пришел airdrop ({level} уровень)! "
                    f"Используйте команду /claim чтобы получить вопрос и заработать баллы."
                )
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Ошибка БД при отправке airdrop: {e}")
        conn.rollback()
    except Exception as e:
        logger.error(f"Ошибка при отправке airdrop: {e}")


# Функция для планирования airdrop
def schedule_airdrop_jobs():
    try:
        # Получаем расписание airdrop из базы данных
        cur.execute("SELECT scheduled_time FROM airdrop_schedule;")
        times = cur.fetchall()

        for t in times:
            scheduled_time = t[0]
            schedule.every().day.at(str(scheduled_time)).do(send_airdrop_to_users)
            logger.info(f"Airdrop запланирован на {scheduled_time} каждый день")
    except psycopg2.Error as e:
        logger.error(f"Ошибка БД при планировании airdrop: {e}")


# Запуск планировщика в отдельном потоке
def run_scheduler():
    schedule_airdrop_jobs()
    while True:
        schedule.run_pending()
        time_module.sleep(60)


if __name__ == "__main__":
    try:
        # Запускаем планировщик airdrop в отдельном потоке
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()

        logger.info("Бот запущен")
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Ошибка в работе бота: {e}")
    finally:
        cur.close()
        conn.close()
        logger.info("Бот остановлен")