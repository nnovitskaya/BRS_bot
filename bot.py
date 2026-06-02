import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
import gspread
import json
from google.oauth2.service_account import Credentials

def get_google_client():
    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

# Загружаем переменные из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ------------------- Работа с Google Sheets -------------------
def get_google_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

def get_user_score(tg_id):
    """Возвращает итоговый балл (столбец L) и выборное направление (столбец M) для данного TG ID"""
    client = get_google_client()
    sheet = client.open_by_key(SHEET_ID).worksheet("пример общей брс")
    # Ищем TG ID во втором столбце (B) - индекс 2 (gspread индексирует с 1)
    cell = sheet.find(str(tg_id), in_column=2)
    if not cell:
        return None, None
    row = cell.row
    score = sheet.cell(row, 12).value  # L - столбец 12
    choice_dir = sheet.cell(row, 13).value if sheet.col_count >= 13 else None  # M - 13
    return score, choice_dir

def get_motivation_text(motiv_type, role_or_direction):
    """Получает текст мотивации из листа 'Мотивация' по типу и роли/направлению"""
    client = get_google_client()
    try:
        sheet = client.open_by_key(SHEET_ID).worksheet("Мотивация")
        records = sheet.get_all_records()
        for rec in records:
            if rec["тип"] == motiv_type and rec["роль/направление"] == role_or_direction:
                return rec["текст мотивации"]
    except Exception as e:
        logging.error(f"Ошибка чтения мотивации: {e}")
    return "✨ Продолжай в том же духе!"  # дефолт

# ------------------- Клавиатуры -------------------
def main_keyboard():
    """Главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мой итоговый балл", callback_data="my_score")],
        [InlineKeyboardButton(text="❤️ Общая мотивация", callback_data="common_motiv")],
        [InlineKeyboardButton(text="🎯 Мотивация по направлениям", callback_data="dir_motiv")]
    ])
    return keyboard

def directions_keyboard(choice_dir):
    """Клавиатура с направлениями, доступными пользователю (обязательные + его выборное)"""
    base_dirs = ["проекты", "уч-соц"]  # обязательные
    dirs = base_dirs.copy()
    if choice_dir and choice_dir in ["информ", "нвс", "нркк"]:
        dirs.append(choice_dir)
    # Создаём кнопки для каждого направления
    buttons = [[InlineKeyboardButton(text=d.capitalize(), callback_data=f"motiv_dir_{d}")] for d in dirs]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ------------------- Обработчики команд -------------------
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    score, choice_dir = get_user_score(user_id)
    if score is None:
        await message.answer("❌ Вы не зарегистрированы в таблице. Обратитесь к руководителю.")
        return
    # Сохраняем выборное направление в данных пользователя? Можно в сессии, но для простоты будем получать каждый раз.
    await message.answer(
        f"👋 Привет, {message.from_user.full_name}!\n"
        f"Твой итоговый балл: {score}\n\n"
        "Выбери действие:",
        reply_markup=main_keyboard()
    )

@dp.callback_query(lambda c: c.data == "my_score")
async def show_score(callback: CallbackQuery):
    user_id = callback.from_user.id
    score, _ = get_user_score(user_id)
    if score is None:
        await callback.message.edit_text("❌ Ошибка: вы не найдены в таблице.")
        return
    # Если балл = "руковод" или что-то подобное, выводим как есть
    await callback.message.edit_text(f"📊 Ваш итоговый балл: **{score}**", parse_mode="Markdown")
    # Через пару секунд вернём главное меню? Можно оставить и предложить кнопку "Назад"
    await callback.message.answer("Вернуться в меню:", reply_markup=main_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "common_motiv")
async def common_motivation(callback: CallbackQuery):
    # Получаем три мотивации
    pred_text = get_motivation_text("общая", "председатель")
    zam_text = get_motivation_text("общая", "первый_зам")
    sek_text = get_motivation_text("общая", "секретарь")
    msg = f"❤️ *Общая мотивация от руководителей:*\n\n"
    msg += f"👑 Председатель: {pred_text}\n\n"
    msg += f"👥 Первый зам: {zam_text}\n\n"
    msg += f"📝 Секретарь: {sek_text}"
    await callback.message.edit_text(msg, parse_mode="Markdown")
    await callback.message.answer("Вернуться в меню:", reply_markup=main_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "dir_motiv")
async def choose_direction(callback: CallbackQuery):
    user_id = callback.from_user.id
    _, choice_dir = get_user_score(user_id)
    if not choice_dir:
        await callback.message.edit_text("❌ Не удалось определить ваше направление. Обратитесь к администратору.")
        return
    keyboard = directions_keyboard(choice_dir)
    await callback.message.edit_text("Выберите направление, чтобы получить мотивацию:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("motiv_dir_"))
async def show_dir_motivation(callback: CallbackQuery):
    direction = callback.data.split("_", 2)[2]  # получаем "проекты", "уч-соц", "информ" и т.д.
    motiv_text = get_motivation_text("направление", direction)
    await callback.message.edit_text(f"🎯 *{direction.capitalize()}*\n\n{motiv_text}", parse_mode="Markdown")
    await callback.message.answer("Вернуться к выбору направления:", reply_markup=directions_keyboard(direction))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_keyboard())
    await callback.answer()

# ------------------- Запуск бота -------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())