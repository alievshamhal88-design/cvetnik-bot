import logging
import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiohttp import web

from config import ADMIN_IDS
from database import Database
from yandex_client import YandexGPTClient

# ============================================
# ФУНКЦИЯ ПРОВЕРКИ НОЧНОГО ВРЕМЕНИ
# ============================================
def is_night_time():
    """Проверяет, ночное ли сейчас время (после 22:00 или до 9:00)"""
    current_hour = datetime.now().hour
    return current_hour >= 22 or current_hour < 9

# ============================================
# КОНСТРУКТОР БУКЕТА - ЦЕНЫ ПО ГРУППАМ
# ============================================
FLOWERS = {
    # ===== РОЗЫ =====
    '🌹 Роза': 260,
    '🌹 Роза Красная': 300,
    '🌹 Роза Крашенная': 360,
    '🌹 Роза Кустовая': 360,
    '🌹 Роза Кустовая Премиум': 460,
    '🌹 Роза Пионовидная': 320,
    '🌹 Роза Премиум': 300,
    '🌹 Роза Французская': 360,
    
    # ===== ХРИЗАНТЕМЫ =====
    '🌸 Ромашка': 200,
    '🌸 Хризантема Куст': 300,
    '🌸 Хризантема Од': 400,
    '🌸 Хризантема Сантини': 280,
    
    # ===== ЭКЗОТИКА =====
    '🌸 Альстромерия': 280,
    '🌸 Антуриум': 800,
    '🌸 Астрантия': 160,
    '🌸 Брассика': 200,
    '🌸 Гвоздика Красная': 130,
    '🌸 Гвоздика Цветная': 160,
    '🌸 Гербера': 260,
    '🌸 Гортензия': 1200,
    '🌸 Дахлия': 300,
    '🌸 Ирис': 200,
    '🌸 Калла': 300,
    '🌸 Лилия': 900,
    '🌸 Орхидея Ветка': 2500,
    '🌸 Орхидея шт': 300,
    '🌸 Пион': 600,
    '🌸 Подсолнух': 400,
    '🌸 Протея': 600,
    '🌸 Седум': 200,
    '🌸 Тюльпан': 200,
    '🌸 Фрезия': 300,
    '🌸 Цветы': 100,
    '🌸 Эустома': 360,
    
    # ===== ЗЕЛЕНЬ =====
    '🌿 Аспидистра': 100,
    '🌿 Ваксфлауер': 160,
    '🌿 Гиперикум': 190,
    '🌿 Гипсафила': 200,
    '🌿 Лимониум': 190,
    '🌿 Матиола': 400,
    '🌿 Нобилис': 100,
    '🌿 Озотамнус': 200,
    '🌿 Пальма': 100,
    '🌿 Папоротник': 100,
    '🌿 Пистация': 200,
    '🌿 Питоспорум': 200,
    '🌿 Рускус': 100,
    '🌿 Солидаго': 150,
    '🌿 Статица': 190,
    '🌿 Твидия': 120,
    '🌿 Трахелиум': 190,
    '🌿 Эвкалипт': 200
}

# ============================================
# ЛОГИРОВАНИЕ
# ============================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# НАСТРОЙКИ БОТА
# ============================================
API_TOKEN = "8462470094:AAHSlSA20IvbGG2AMOBDL9qk3eqXakzuwWg"

# Инициализация YandexGPT
try:
    yandex_gpt = YandexGPTClient()
    logger.info("✅ YandexGPT клиент создан")
except ValueError as e:
    logger.error(f"❌ Ошибка создания YandexGPT клиента: {e}")
    yandex_gpt = None

# Филиалы
BRANCHES = {
    '2-я Марата, 22': {'id': 7364255009, 'username': '@cvetnik_sib'},
    'Некрасова, 41': {'id': 7651760894, 'username': '@cvetnik1_sib'},
    'Связистов, 113А': {'id': 8575692209, 'username': '@cvetniksvezistrov'}
}

# ============================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ============================================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
db = Database()

# ============================================
# СОСТОЯНИЯ
# ============================================
STATE_IDLE = 0
STATE_WAITING_PRODUCT = 1
STATE_WAITING_CLIENT_NAME = 2
STATE_WAITING_CLIENT_PHONE = 3
STATE_WAITING_ADDRESS = 4
STATE_WAITING_RECIPIENT_NAME = 5
STATE_WAITING_RECIPIENT_PHONE = 6
STATE_WAITING_RECIPIENT_PHONE_INPUT = 9
STATE_WAITING_CARD_TEXT = 7
STATE_WAITING_BRANCH = 8
STATE_BIRTHDAY_WAITING = 100
STATE_SUB_RECIPIENT = 101
STATE_SUB_PHONE = 102
STATE_SUB_ADDRESS = 103
STATE_SUB_FREQUENCY = 104
STATE_SUB_BUDGET = 105
STATE_SUB_CONFIRM = 106

# Конструктор букета
STATE_CONSTRUCTOR_STEP_1 = 201  # выбор цветов
STATE_CONSTRUCTOR_STEP_2 = 202  # подтверждение

user_data = {}
user_states = {}

# ============================================
# КЛАВИАТУРЫ
# ============================================
client_phone_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True
)

recipient_phone_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Такой же, как у клиента")],
        [KeyboardButton(text="✏️ Ввести другой номер")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

card_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 Написать текст")],
        [KeyboardButton(text="⏭️ Без открытки")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

branch_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏢 2-я Марата, 22")],
        [KeyboardButton(text="🏢 Некрасова, 41")],
        [KeyboardButton(text="🏢 Связистов, 113А")]
    ],
    resize_keyboard=True
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛒 Оформить заказ")],
        [KeyboardButton(text="🎨 Собрать свой букет")],
        [KeyboardButton(text="🌸 Выбрать букет из каталога")],
        [KeyboardButton(text="🎂 Сохранить день рождения")],
        [KeyboardButton(text="📦 Цветочная подписка")],
        [KeyboardButton(text="📞 Связаться с флористом")],
        [KeyboardButton(text="ℹ️ О нас")]
    ],
    resize_keyboard=True
)

# ============================================
# ПИНГ-СЕРВЕР
# ============================================
async def handle_ping(request):
    return web.Response(text='OK')

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/ping', handle_ping)
    app.router.add_get('/health', handle_ping)
    port = int(os.environ.get('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"✅ Пинг-сервер запущен на порту {port}")

# ============================================
# КОМАНДА START
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_IDLE
    user_data[user_id] = {}
    await message.answer(
        "🌸 Добро пожаловать в «Цветник»!\n\n"
        "Я помогу быстро заказать букет с доставкой по Новосибирску.\n\n"
        "👇 Выберите действие в меню ниже",
        reply_markup=main_keyboard
    )

@dp.message(Command("test"))
async def test_handler(message: types.Message):
    await message.answer(f"✅ Тест работает! Ваш ID: {message.from_user.id}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Показывает статистику каталога"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав администратора")
        return
    
    count = db.get_bouquets_count()
    await message.answer(
        f"📊 **Статистика каталога**\n\n"
        f"🌸 Всего букетов: {count}",
        parse_mode='Markdown'
    )

# ============================================
# КОНСТРУКТОР БУКЕТА
# ============================================
@dp.message(F.text == "🎨 Собрать свой букет")
async def constructor_start(message: types.Message):
    user_id = message.from_user.id
    
    # Ночной режим
    if is_night_time():
        await message.answer(
            "🌙 **Ночной режим**\n\n"
            "🕒 Сейчас наш рабочий день закончен, но вы можете собрать букет!\n"
            "✅ Мы начнём собирать ваш заказ завтра в **9:00 утра**.",
            parse_mode='Markdown'
        )
    
    # Инициализируем данные для конструктора
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]['constructor'] = {
        'flowers': [],
        'total': 0
    }
    
    # Формируем списки по группам
    roses = [name for name in FLOWERS.keys() if name.startswith('🌹')]
    chrys = [name for name in FLOWERS.keys() if name.startswith('🌸') and 'Хризантема' in name]
    exotic = [name for name in FLOWERS.keys() if name.startswith('🌸') and name not in chrys and 'Ромашка' not in name]
    greens = [name for name in FLOWERS.keys() if name.startswith('🌿')]
    
    roses_list = "\n".join([f"• {name} — {FLOWERS[name]}₽" for name in sorted(roses)])
    chrys_list = "\n".join([f"• {name} — {FLOWERS[name]}₽" for name in sorted(chrys)])
    exotic_list = "\n".join([f"• {name} — {FLOWERS[name]}₽" for name in sorted(exotic)[:15]]) + "\n... и другие"
    greens_list = "\n".join([f"• {name} — {FLOWERS[name]}₽" for name in sorted(greens)[:15]]) + "\n... и другие"
    
    await message.answer(
        "🎨 **Конструктор букета**\n\n"
        "Выберите цветы для вашего букета. Можно выбрать несколько.\n\n"
        "🌹 **РОЗЫ:**\n"
        f"{roses_list}\n\n"
        "🌸 **ХРИЗАНТЕМЫ:**\n"
        f"{chrys_list}\n\n"
        "✨ **ЭКЗОТИКА:**\n"
        f"{exotic_list}\n\n"
        "🌿 **ЗЕЛЕНЬ:**\n"
        f"{greens_list}\n\n"
        "📝 **Как выбрать:** напишите названия цветов через запятую.\n"
        "Например: `🌹 Роза Красная, 🌸 Пион, 🌿 Эвкалипт`\n\n"
        "📦 **Упаковку подберёт флорист** под ваш букет!",
        parse_mode='Markdown'
    )
    user_states[user_id] = STATE_CONSTRUCTOR_STEP_1

@dp.message(F.text)
async def constructor_handle_flowers(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    # Проверяем, что мы в конструкторе
    if user_states.get(user_id) != STATE_CONSTRUCTOR_STEP_1:
        return
    
    # Разбираем выбранные цветы
    selected = [item.strip() for item in text.split(',')]
    valid_flowers = []
    total = 0
    not_found = []
    
    for flower in selected:
        flower_clean = flower.replace('🌹', '').replace('🌸', '').replace('🌿', '').strip()
        
        found = False
        for db_flower in FLOWERS.keys():
            db_clean = db_flower.replace('🌹', '').replace('🌸', '').replace('🌿', '').strip()
            if flower_clean.lower() in db_clean.lower() or db_clean.lower() in flower_clean.lower():
                valid_flowers.append(db_flower)
                total += FLOWERS[db_flower]
                found = True
                break
        if not found:
            not_found.append(flower)
    
    if not valid_flowers:
        await message.answer(
            "❌ Не найдено таких цветов. Пожалуйста, выбирайте из списка.\n"
            "Например: `🌹 Роза Красная, 🌸 Пион, 🌿 Эвкалипт`"
        )
        return
    
    # Сохраняем выбранные цветы
    user_data[user_id]['constructor']['flowers'] = valid_flowers
    user_data[user_id]['constructor']['total'] = total
    
    # Группируем для красивого вывода
    result_roses = [f for f in valid_flowers if f.startswith('🌹')]
    result_chrys = [f for f in valid_flowers if f.startswith('🌸') and 'Хризантема' in f]
    result_exotic = [f for f in valid_flowers if f.startswith('🌸') and f not in result_chrys]
    result_greens = [f for f in valid_flowers if f.startswith('🌿')]
    
    result_text = ""
    if result_roses:
        result_text += "🌹 **Розы:**\n" + "\n".join([f"• {f}" for f in result_roses]) + "\n\n"
    if result_chrys:
        result_text += "🌸 **Хризантемы:**\n" + "\n".join([f"• {f}" for f in result_chrys]) + "\n\n"
    if result_exotic:
        result_text += "✨ **Экзотика:**\n" + "\n".join([f"• {f}" for f in result_exotic]) + "\n\n"
    if result_greens:
        result_text += "🌿 **Зелень:**\n" + "\n".join([f"• {f}" for f in result_greens]) + "\n\n"
    
    await message.answer(
        f"✅ **Ваш букет готов!**\n\n"
        f"{result_text}"
        f"💰 **Стоимость цветов: {total}₽**\n"
        f"📦 **Упаковка:** подберёт флорист под ваш букет\n\n"
        f"Теперь продолжим оформление заказа.",
        parse_mode='Markdown'
    )
    
    # Сохраняем как продукт для заказа
    product_name = f"Букет (конструктор): {', '.join([f.split(' ')[-1] for f in valid_flowers[:3]])} и др."
    product_desc = f"Состав: {', '.join(valid_flowers)}. Упаковка подбирается флористом."
    
    user_data[user_id]['product'] = product_name
    user_data[user_id]['product_description'] = product_desc
    user_data[user_id]['product_source'] = 'constructor'
    user_data[user_id]['price'] = total
    
    # Переходим к имени клиента
    await message.answer("📝 Теперь напишите ваше имя:")
    user_states[user_id] = STATE_WAITING_CLIENT_NAME

# ============================================
# ЗАГРУЗКА ФОТО АДМИНИСТРАТОРОМ
# ============================================
@dp.message(F.photo)
async def handle_admin_photo(message: types.Message):
    """Администратор загружает фото для каталога"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав администратора")
        return
    
    try:
        photo = message.photo[-1]
        file_id = photo.file_id
        
        file_info = await bot.get_file(file_id)
        file_path = f"data/bouquets/{file_id}.jpg"
        await bot.download_file(file_info.file_path, file_path)
        
        success = db.add_bouquet(file_id, file_path)
        
        if success:
            count = db.get_bouquets_count()
            await message.answer(f"✅ Фото добавлено в каталог! Всего букетов: {count}")
        else:
            await message.answer("❌ Ошибка при сохранении")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await message.answer(f"❌ Ошибка: {e}")

# ============================================
# ВЫБОР БУКЕТА ИЗ КАТАЛОГА
# ============================================
@dp.message(F.text == "🌸 Выбрать букет из каталога")
async def catalog_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌸 Открыть каталог на сайте", url="https://cvetniknsk.ru")]
    ])
    
    await message.answer(
        "🌸 **Выбрать букет**\n\n"
        "Все наши букеты вы можете посмотреть на сайте.\n"
        "После выбора возвращайтесь в бот для оформления заказа!",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

# ============================================
# ОФОРМЛЕНИЕ ЗАКАЗА
# ============================================
@dp.message(F.text == "🛒 Оформить заказ")
async def order_start(message: types.Message):
    user_id = message.from_user.id
    
    # Ночной режим
    if is_night_time():
        await message.answer(
            "🌙 **Ночной режим**\n\n"
            "🕒 Сейчас наш рабочий день закончен, но вы можете оформить заказ!\n"
            "✅ Мы начнём собирать ваш букет завтра в **9:00 утра**.",
            parse_mode='Markdown'
        )
    
    user_states[user_id] = STATE_WAITING_PRODUCT
    user_data[user_id] = {}
    
    catalog_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌸 Открыть каталог на сайте", url="https://cvetniknsk.ru")]
    ])
    
    await message.answer(
        "🌸 **Выберите букет** одним из способов:\n\n"
        "📸 **Пришлите фото** понравившегося букета\n"
        "📝 **Напишите название** или описание\n"
        "🎨 **Или соберите свой букет** по кнопке в меню\n"
        "📱 **Или выберите из нашего каталога** по кнопке ниже",
        reply_markup=catalog_keyboard,
        parse_mode='Markdown'
    )

# ============================================
# ОБРАБОТКА КОНТАКТА
# ============================================
@dp.message(F.contact)
async def handle_client_phone(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"📱 Получен контакт от пользователя {user_id}")
    
    current_state = user_states.get(user_id)
    
    if current_state != STATE_WAITING_CLIENT_PHONE:
        logger.warning(f"❌ Неверное состояние: {current_state}")
        await message.answer("Пожалуйста, начните оформление заказа сначала.")
        return
    
    phone = message.contact.phone_number
    user_data[user_id]['client_phone'] = phone
    user_states[user_id] = STATE_WAITING_ADDRESS
    
    await message.answer(
        "✅ Номер получен!\n\n"
        "📝 Напишите адрес доставки и желаемое время:\n"
        "Например: ул. Некрасова, 41, кв. 5, сегодня к 18:00",
        reply_markup=ReplyKeyboardRemove()
    )

# ============================================
# ДНИ РОЖДЕНИЯ
# ============================================
@dp.message(F.text == "🎂 Сохранить день рождения")
async def birthday_start(message: types.Message):
    await message.answer(
        "🎂 **Сохраним день рождения вашего близкого!**\n\n"
        "➕ **И получите персональную скидку 10%** на заказ в этот день!\n\n"
        "Введите дату и имя в формате:\n"
        "`ДД.ММ имя`\n\n"
        "Например: `15.05 мама` или `23.02 папа`",
        parse_mode='Markdown'
    )
    user_states[message.from_user.id] = STATE_BIRTHDAY_WAITING

# ============================================
# ЦВЕТОЧНАЯ ПОДПИСКА
# ============================================
@dp.message(F.text == "📦 Цветочная подписка")
async def subscription_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Оформить подписку", callback_data="sub_new")],
        [InlineKeyboardButton(text="❓ Как это работает", callback_data="sub_info")]
    ])
    await message.answer(
        "🌸 **Цветочная подписка**\n\n"
        "Регулярные букеты для ваших близких без лишних забот.\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@dp.callback_query(F.data == "sub_new")
async def subscription_new(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data[user_id] = user_data.get(user_id, {})
    user_states[user_id] = STATE_SUB_RECIPIENT
    await callback.message.edit_text(
        "📦 **Оформление подписки**\n\n"
        "**Шаг 1 из 4**\n"
        "Кому вы хотите отправлять цветы? Введите имя получателя:"
    )
    await callback.answer()

@dp.callback_query(F.data == "sub_info")
async def subscription_info(callback: types.CallbackQuery):
    text = (
        "🌸 **Как работает подписка**\n\n"
        "1. Вы указываете получателя и бюджет\n"
        "2. Выбираете частоту\n"
        "3. В указанный день я напомню о заказе"
    )
    await callback.message.answer(text)
    await callback.answer()

# ============================================
# СВЯЗАТЬСЯ С ФЛОРИСТОМ
# ============================================
@dp.message(F.text == "📞 Связаться с флористом")
async def contact_florist(message: types.Message):
    await message.answer(
        "📞 **Контакты наших филиалов:**\n\n"
        "🏢 **2-я Марата, 22**\n📱 +7‒995‒390‒12‒02\n\n"
        "🏢 **Некрасова, 41**\n📱 +7‒995‒390‒23‒55\n\n"
        "🏢 **Связистов, 113а**\n📱 +7‒993‒952‒23‒55\n\n"
        "📧 Email: cvetniknsk@yandex.ru",
        parse_mode='Markdown',
        reply_markup=main_keyboard
    )

# ============================================
# О НАС
# ============================================
@dp.message(F.text == "ℹ️ О нас")
async def about(message: types.Message):
    await message.answer(
        "🌸 **«Цветник»** — сеть студий цветов в Новосибирске\n\n"
        "📍 **Наши адреса:**\n• 2-я Марата, 22\n• Некрасова, 41\n• Связистов, 113А\n\n"
        "📞 **Телефон:** +7‒995‒390‒23‒55\n\n"
        "🕒 **Работаем ежедневно** с 9:00 до 22:00\n"
        "🚚 **Доставка** по городу от 500₽\n\n"
        "📍 **Мы на 2ГИС:** [Открыть в 2ГИС](https://2gis.ru/novosibirsk/branches/70000001091590889)",
        parse_mode='Markdown',
        reply_markup=main_keyboard,
        disable_web_page_preview=True
    )

# ============================================
# ОБРАБОТКА ТЕКСТА
# ============================================
@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    # Пропускаем главные кнопки
    if text in ["🛒 Оформить заказ", "🌸 Выбрать букет из каталога", 
                "🎂 Сохранить день рождения", "📦 Цветочная подписка",
                "📞 Связаться с флористом", "ℹ️ О нас", "🎨 Собрать свой букет"]:
        return
    
    state = user_states.get(user_id)
    
    # Если мы в конструкторе - выходим
    if state == STATE_CONSTRUCTOR_STEP_1:
        return
    
    # Шаги подписки
    if state == STATE_SUB_RECIPIENT:
        user_data[user_id]['sub_recipient'] = text
        user_states[user_id] = STATE_SUB_PHONE
        await message.answer("📞 **Шаг 2 из 4**\nВведите телефон получателя (или /skip):")
        return
    
    if state == STATE_SUB_PHONE:
        if text != '/skip':
            user_data[user_id]['sub_phone'] = text
        user_states[user_id] = STATE_SUB_ADDRESS
        await message.answer("📍 **Шаг 3 из 4**\nВведите адрес получателя (или /skip):")
        return
    
    if state == STATE_SUB_ADDRESS:
        if text != '/skip':
            user_data[user_id]['sub_address'] = text
        user_states[user_id] = STATE_SUB_FREQUENCY
        await message.answer("📅 **Шаг 4 из 4**\nКак часто отправлять? (раз в месяц/неделю)")
        return
    
    if state == STATE_SUB_FREQUENCY:
        user_data[user_id]['sub_frequency'] = text
        user_states[user_id] = STATE_SUB_BUDGET
        await message.answer("💰 **Шаг 5 из 5**\nКакой бюджет на один букет? (в рублях)")
        return
    
    if state == STATE_SUB_BUDGET:
        try:
            budget = int(text.replace('₽', '').replace(' ', ''))
            user_data[user_id]['sub_budget'] = budget
            
            sub_data = {
                'user_id': user_id,
                'recipient_name': user_data[user_id].get('sub_recipient', ''),
                'recipient_phone': user_data[user_id].get('sub_phone', ''),
                'recipient_address': user_data[user_id].get('sub_address', ''),
                'frequency': user_data[user_id].get('sub_frequency', ''),
                'budget': budget,
                'auto_confirm': 0,
                'next_date': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            }
            
            sub_id = db.add_subscription(sub_data)
            
            if sub_id:
                await message.answer(
                    "✅ **Подписка оформлена!**\n\n"
                    f"Получатель: {sub_data['recipient_name']}\n"
                    f"Бюджет: {budget} ₽",
                    reply_markup=main_keyboard
                )
            else:
                await message.answer("❌ Ошибка при оформлении подписки")
            
            user_states[user_id] = STATE_IDLE
        except Exception as e:
            await message.answer("❌ Введите число (например: 3000)")
        return
    
    # Шаги заказа
    if state == STATE_WAITING_PRODUCT:
        user_data[user_id]['product'] = text
        user_states[user_id] = STATE_WAITING_CLIENT_NAME
        await message.answer("📝 Напишите ваше имя:")
        return
    
    if state == STATE_WAITING_CLIENT_NAME:
        user_data[user_id]['client_name'] = text
        user_states[user_id] = STATE_WAITING_CLIENT_PHONE
        await message.answer(
            f"✅ Имя записано!\n\n📱 Отправьте ваш номер телефона:",
            reply_markup=client_phone_keyboard
        )
        return
    
    if state == STATE_WAITING_ADDRESS:
        user_data[user_id]['address'] = text
        user_states[user_id] = STATE_WAITING_RECIPIENT_NAME
        await message.answer("👤 Напишите имя получателя:")
        return
    
    if state == STATE_WAITING_RECIPIENT_NAME:
        user_data[user_id]['recipient_name'] = text
        user_states[user_id] = STATE_WAITING_RECIPIENT_PHONE
        await message.answer(
            f"✅ Имя получателя: {text}\n\n"
            f"📱 Выберите вариант для телефона получателя:",
            reply_markup=recipient_phone_keyboard
        )
        return
    
    if state == STATE_WAITING_RECIPIENT_PHONE:
        if text == "📱 Такой же, как у клиента":
            user_data[user_id]['recipient_phone'] = user_data[user_id]['client_phone']
            user_states[user_id] = STATE_WAITING_CARD_TEXT
            await message.answer(
                "💌 Напишите текст для открытки (или пропустите):",
                reply_markup=card_keyboard
            )
        elif text == "✏️ Ввести другой номер":
            user_states[user_id] = STATE_WAITING_RECIPIENT_PHONE_INPUT
            await message.answer("📱 Введите номер телефона получателя:")
        return
    
    if state == STATE_WAITING_RECIPIENT_PHONE_INPUT:
        user_data[user_id]['recipient_phone'] = text
        user_states[user_id] = STATE_WAITING_CARD_TEXT
        await message.answer(
            "💌 Напишите текст для открытки (или пропустите):",
            reply_markup=card_keyboard
        )
        return
    
    if state == STATE_WAITING_CARD_TEXT:
        if text == "⏭️ Без открытки":
            user_data[user_id]['card_text'] = "Без открытки"
        else:
            user_data[user_id]['card_text'] = text
        user_states[user_id] = STATE_WAITING_BRANCH
        await message.answer(
            "📍 Выберите удобный филиал:",
            reply_markup=branch_keyboard
        )
        return
    
    if state == STATE_WAITING_BRANCH:
        branch_map = {
            "🏢 2-я Марата, 22": "2-я Марата, 22",
            "🏢 Некрасова, 41": "Некрасова, 41",
            "🏢 Связистов, 113А": "Связистов, 113А"
        }
        
        if text in branch_map:
            user_data[user_id]['branch'] = branch_map[text]
            await send_order_to_florist(message, user_id)
            await message.answer(
                f"✅ **ЗАКАЗ ПРИНЯТ!**\n\n"
                f"🌸 Букет: {user_data[user_id]['product']}\n"
                f"👤 Получатель: {user_data[user_id]['recipient_name']}\n"
                f"📍 Адрес: {user_data[user_id]['address']}\n"
                f"🏢 Филиал: {branch_map[text]}\n"
                f"💌 Открытка: {user_data[user_id].get('card_text', 'Без открытки')}",
                parse_mode='Markdown',
                reply_markup=main_keyboard
            )
            user_states[user_id] = STATE_IDLE
        else:
            await message.answer("Пожалуйста, выберите вариант из меню:")
        return
    
    # День рождения
    if state == STATE_BIRTHDAY_WAITING:
        try:
            parts = text.split(' ', 1)
            if len(parts) != 2:
                raise ValueError("Неверный формат")
            
            date_str = parts[0]
            name = parts[1]
            date_obj = datetime.strptime(date_str, '%d.%m')
            month_day = date_obj.strftime('%m-%d')
            db.add_birthday(user_id, name, month_day)
            
            await message.answer(
                f"✅ Готово! Я запомнил день рождения {name} — {date_str}.\n\n"
                f"За 3 дня до даты я напомню вам и предложу персональную скидку 10%!",
                reply_markup=main_keyboard
            )
            user_states[user_id] = STATE_IDLE
        except Exception as e:
            await message.answer(
                "❌ Неправильный формат. Попробуйте ещё раз, например:\n"
                "`15.05 мама`",
                parse_mode='Markdown'
            )
        return

# ============================================
# ОТПРАВКА ЗАКАЗА В ФИЛИАЛ
# ============================================
async def send_order_to_florist(message: types.Message, user_id: int):
    client_name = user_data[user_id].get('client_name', 'Не указано')
    username = message.from_user.username or "Нет username"
    
    product_info = user_data[user_id]['product']
    product_desc = user_data[user_id].get('product_description', '')
    
    # Проверяем время для ночного режима
    night_order = "🌙 НОЧНОЙ ЗАКАЗ\n" if is_night_time() else ""
    
    order_text = (
        f"🌸 НОВЫЙ ЗАКАЗ 🌸\n"
        f"{night_order}"
        f"==================\n\n"
        f"👤 Клиент: {client_name}\n"
        f"📱 Телефон: {user_data[user_id]['client_phone']}\n"
        f"👤 Получатель: {user_data[user_id].get('recipient_name', 'Не указано')}\n"
        f"📱 Телефон получателя: {user_data[user_id].get('recipient_phone', 'Не указано')}\n"
        f"📍 Адрес: {user_data[user_id]['address']}\n"
        f"🌸 Букет: {product_info}\n"
        f"📝 Описание: {product_desc}\n"
    )
    
    if user_data[user_id].get('card_text'):
        order_text += f"💌 Открытка: {user_data[user_id]['card_text']}\n"
    
    chosen_branch = user_data[user_id]['branch']
    order_text += f"🏢 Филиал: {chosen_branch}\n🆔 @{username}"
    
    # Отправляем в выбранный филиал
    florist_id = BRANCHES[chosen_branch]['id']
    try:
        await bot.send_message(chat_id=florist_id, text=order_text)
        logger.info(f"✅ Заказ отправлен в филиал {chosen_branch}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в {chosen_branch}: {e}")
        await message.answer("⚠️ Произошла ошибка, но мы уже знаем о проблеме. Флорист скоро свяжется!")

# ============================================
# ЗАПУСК
# ============================================
async def main():
    asyncio.create_task(run_web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Вебхук сброшен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
