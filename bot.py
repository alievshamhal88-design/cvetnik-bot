import logging
import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiohttp import web

from config import ADMIN_IDS, GEMINI_MODELS
from database import Database

# ============================================
# НАСТРОЙКИ БОТА
# ============================================
API_TOKEN = "8462470094:AAHSlSA20IvbGG2AMOBDL9qk3eqXakzuwWg"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY не найден в переменных окружения!")

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)

BRANCHES = {
    '2-я Марата, 22': {'id': 7364255009, 'username': '@cvetnik_sib', 'is_admin': False},
    'Некрасова, 41': {'id': 7651760894, 'username': '@cvetnik1_sib', 'is_admin': True},
    'Связистов, 113А': {'id': 8575692209, 'username': '@cvetniksvezistrov', 'is_admin': False}
}

# ============================================
# ЛОГИРОВАНИЕ
# ============================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# ИНИЦИАЛИЗАЦИЯ
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

# Новые состояния
STATE_BIRTHDAY_WAITING = 100
STATE_SUB_RECIPIENT = 101
STATE_SUB_PHONE = 102
STATE_SUB_ADDRESS = 103
STATE_SUB_FREQUENCY = 104
STATE_SUB_BUDGET = 105
STATE_SUB_CONFIRM = 106

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
        [KeyboardButton(text="🏢 Связистов, 113А")],
        [KeyboardButton(text="🚚 Доставка")]
    ],
    resize_keyboard=True
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛒 Оформить заказ")],
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
# ФУНКЦИИ ДЛЯ GEMINI
# ============================================
async def generate_with_fallback(prompt, image=None, max_retries=3):
    """Генерирует текст с fallback на разные модели"""
    
    for attempt in range(max_retries):
        for model_name in GEMINI_MODELS:
            try:
                model = genai.GenerativeModel(model_name)
                
                if image:
                    response = model.generate_content([prompt, image])
                else:
                    response = model.generate_content(prompt)
                
                if response and response.text:
                    return response.text.strip()
                    
            except Exception as e:
                logger.warning(f"⚠️ Ошибка с моделью {model_name}: {e}")
                continue
        
        await asyncio.sleep(1)
    
    return None

async def generate_bouquet_info(photo_file_id):
    """
    Gemini смотрит на фото и генерирует название и описание
    """
    try:
        # Скачиваем фото
        file_info = await bot.get_file(photo_file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        
        # Открываем изображение
        image = Image.open(BytesIO(file_bytes.read()))
        
        # Промпт для Gemini
        prompt = (
            "Посмотри на это фото букета цветов. Напиши для него:\n\n"
            "1. КРАСИВОЕ НАЗВАНИЕ (2-4 слова, поэтичное, на русском)\n"
            "2. КОРОТКОЕ ОПИСАНИЕ (2-3 предложения о букете: какие цветы, "
            "какое настроение, для какого повода подойдёт)\n\n"
            "Формат ответа (строго соблюдай):\n"
            "Название: ...\n"
            "Описание: ..."
        )
        
        # Отправляем в Gemini
        result = await generate_with_fallback(prompt, image)
        
        if result:
            # Парсим ответ
            lines = result.split('\n')
            name = "Волшебный букет"
            description = "Нежный букет для особенного случая."
            
            for line in lines:
                if line.startswith('Название:'):
                    name = line.replace('Название:', '').strip()
                elif line.startswith('Описание:'):
                    description = line.replace('Описание:', '').strip()
            
            return name, description
        
    except Exception as e:
        logger.error(f"❌ Ошибка Gemini: {e}")
    
    # Запасные варианты
    fallback_names = [
        "Нежность утра", "Цветочная симфония", "Весеннее настроение",
        "Аромат любви", "Солнечный день", "Летний сад"
    ]
    fallback_desc = [
        "Нежный букет из свежих цветов, собранный с любовью.",
        "Яркий букет, который подарит радость и хорошее настроение.",
        "Изысканная композиция для особенного случая."
    ]
    
    return random.choice(fallback_names), random.choice(fallback_desc)

# ============================================
# ОБРАБОТЧИКИ ФОТО (ДЛЯ АДМИНА)
# ============================================
@dp.message(F.photo)
async def handle_admin_photo(message: types.Message):
    """Администратор загружает фото для каталога"""
    user_id = message.from_user.id
    
    # Проверяем права
    if user_id not in ADMIN_IDS:
        return
    
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # Сохраняем фото локально
    file_info = await bot.get_file(file_id)
    file_path = f"data/bouquets/{file_id}.jpg"
    await bot.download_file(file_info.file_path, file_path)
    
    # Добавляем в базу (без названия, оно сгенерируется позже)
    db.add_bouquet(file_id, file_path)
    
    await message.answer(
        f"✅ Фото добавлено в каталог!\n"
        f"ID: {file_id}\n"
        f"Всего букетов: {db.get_bouquets_count()}"
    )

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

# ============================================
# ТЕСТОВАЯ КОМАНДА
# ============================================
@dp.message(Command("test"))
async def test_handler(message: types.Message):
    await message.answer(f"✅ Тест работает! Ваш ID: {message.from_user.id}")

# ============================================
# МОДУЛЬ: ВЫБОР БУКЕТА ИЗ КАТАЛОГА
# ============================================
@dp.message(F.text == "🌸 Выбрать букет из каталога")
async def catalog_start(message: types.Message):
    """Показывает 3 случайных букета с AI-названиями"""
    user_id = message.from_user.id
    
    # Проверяем, есть ли букеты
    if db.get_bouquets_count() == 0:
        await message.answer("😢 В каталоге пока нет букетов. Скоро добавим!")
        return
    
    # Отправляем 3 букета
    for i in range(3):
        bouquet = db.get_random_bouquet()
        if not bouquet:
            continue
        
# Генерируем название и описание через Gemini
status_msg = await message.answer(f"🌸 Подбираем для вас лучший букет... ✨")
        
        name, description = await generate_bouquet_info(bouquet['photo_file_id'])
        
        await status_msg.delete()
        
        # Сохраняем в данные пользователя
        user_data[user_id] = user_data.get(user_id, {})
        user_data[user_id][f'b_name_{i}'] = name
        user_data[user_id][f'b_desc_{i}'] = description
        user_data[user_id][f'b_id_{i}'] = bouquet['id']
        
        # Создаём кнопку
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выбрать этот букет", callback_data=f"select_{i}")]
        ])
        
        # Отправляем фото с названием и описанием
        caption = f"🌸 **{name}**\n\n{description}"
        
        await message.answer_photo(
            photo=bouquet['photo_file_id'],
            caption=caption,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

@dp.callback_query(F.data.startswith('select_'))
async def select_bouquet(callback: types.CallbackQuery):
    """Обработка выбора букета"""
    index = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    
    # Получаем данные выбранного букета
    name = user_data.get(user_id, {}).get(f'b_name_{index}', "Выбранный букет")
    desc = user_data.get(user_id, {}).get(f'b_desc_{index}', "")
    bouquet_id = user_data.get(user_id, {}).get(f'b_id_{index}')
    
    # Сохраняем в заказ
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]['product'] = name
    user_data[user_id]['product_description'] = desc
    user_data[user_id]['product_source'] = 'catalog_ai'
    user_data[user_id]['selected_bouquet_id'] = bouquet_id
    
    await callback.message.answer(
        f"✅ Вы выбрали: **{name}**\n\n"
        f"📝 Теперь напишите ваше имя:",
        parse_mode='Markdown'
    )
    user_states[user_id] = STATE_WAITING_CLIENT_NAME
    await callback.answer()

# ============================================
# МОДУЛЬ: ДНИ РОЖДЕНИЯ
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

@dp.message(F.text)
async def handle_birthday_input(message: types.Message):
    user_id = message.from_user.id
    if user_states.get(user_id) != STATE_BIRTHDAY_WAITING:
        return
    
    text = message.text.strip()
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

# ============================================
# МОДУЛЬ: ЦВЕТОЧНАЯ ПОДПИСКА
# ============================================
@dp.message(F.text == "📦 Цветочная подписка")
async def subscription_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Оформить подписку", callback_data="sub_new")],
        [InlineKeyboardButton(text="📋 Мои подписки", callback_data="sub_list")],
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
        "**Шаг 1 из 5**\n"
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
# ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (ЗАКАЗ)
# ============================================
@dp.message(F.text == "🛒 Оформить заказ")
async def order_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_WAITING_PRODUCT
    user_data[user_id] = {}
    
    catalog_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌸 Открыть каталог на сайте", url="https://cvetniknsk.ru")]
    ])
    
    await message.answer(
        "🌸 **Выберите букет** одним из способов:\n\n"
        "📸 **Пришлите фото** понравившегося букета\n"
        "📝 **Напишите название** или описание\n"
        "📱 **Или выберите из нашего каталога** по кнопке ниже",
        reply_markup=catalog_keyboard,
        parse_mode='Markdown'
    )

@dp.message(F.text == "📞 Связаться с флористом")
async def contact_florist(message: types.Message):
    await message.answer(
        "📞 **Контакты наших филиалов:**\n\n"
        "🏢 **Некрасова, 41**\n📱 +7‒995‒390‒23‒55\n\n"
        "🏢 **2-я улица Марата, 22**\n📱 +7‒995‒390‒12‒02\n\n"
        "🏢 **Улица Связистов, 113а**\n📱 +7‒993‒952‒23‒55\n\n"
        "📧 Email: cvetniknsk@yandex.ru",
        parse_mode='Markdown',
        reply_markup=main_keyboard
    )

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

@dp.message(F.contact)
async def handle_client_phone(message: types.Message):
    user_id = message.from_user.id
    if user_states.get(user_id) != STATE_WAITING_CLIENT_PHONE:
        return
    
    user_data[user_id]['client_phone'] = message.contact.phone_number
    user_states[user_id] = STATE_WAITING_ADDRESS
    
    await message.answer(
        "✅ Номер получен!\n\n"
        "📝 Напишите адрес доставки и желаемое время:\n"
        "Например: ул. Некрасова, 41, кв. 5, сегодня к 18:00",
        reply_markup=ReplyKeyboardRemove()
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
                "📞 Связаться с флористом", "ℹ️ О нас"]:
        return
    
    state = user_states.get(user_id)
    
    # Шаги подписки
    if state == STATE_SUB_RECIPIENT:
        user_data[user_id]['sub_recipient'] = text
        user_states[user_id] = STATE_SUB_PHONE
        await message.answer("📞 **Шаг 2 из 5**\nВведите телефон получателя:")
        return
    
    if state == STATE_SUB_PHONE:
        user_data[user_id]['sub_phone'] = text
        user_states[user_id] = STATE_SUB_ADDRESS
        await message.answer("📍 **Шаг 3 из 5**\nВведите адрес получателя:")
        return
    
    if state == STATE_SUB_ADDRESS:
        user_data[user_id]['sub_address'] = text
        user_states[user_id] = STATE_SUB_FREQUENCY
        await message.answer("📅 **Шаг 4 из 5**\nКак часто отправлять? (раз в месяц/неделю)")
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
            
            # Сохраняем подписку
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
            "🏢 Связистов, 113А": "Связистов, 113А",
            "🚚 Доставка": "доставка"
        }
        if text in branch_map:
            user_data[user_id]['branch'] = branch_map[text]
            await send_order_to_florist(message, user_id)
            await message.answer(
                f"✅ **ЗАКАЗ ПРИНЯТ!**\n\n"
                f"🌸 Букет: {user_data[user_id]['product']}\n"
                f"👤 Получатель: {user_data[user_id]['recipient_name']}\n"
                f"📍 Адрес: {user_data[user_id]['address']}\n"
                f"🏢 {branch_map[text]}\n"
                f"💌 Открытка: {user_data[user_id].get('card_text', 'Без открытки')}",
                parse_mode='Markdown',
                reply_markup=main_keyboard
            )
            user_states[user_id] = STATE_IDLE
        else:
            await message.answer("Пожалуйста, выберите вариант из меню:")

# ============================================
# ОТПРАВКА ЗАКАЗА ФЛОРИСТАМ
# ============================================
async def send_order_to_florist(message: types.Message, user_id: int):
    client_name = user_data[user_id].get('client_name', 'Не указано')
    username = message.from_user.username or "Нет username"
    
    product_info = user_data[user_id]['product']
    product_desc = user_data[user_id].get('product_description', '')
    
    order_text = (
        f"🌸 НОВЫЙ ЗАКАЗ 🌸\n\n"
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
    
    order_text += f"🏢 Филиал: {user_data[user_id]['branch']}\n🆔 @{username}"

    branch = user_data[user_id]['branch']
    admin_id = 7651760894
    
    # Администратору
    try:
        await bot.send_message(chat_id=admin_id, text=order_text)
        logger.info(f"✅ Администратору {admin_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка админу: {e}")

    # Филиалам
    if branch == "доставка":
        for name, info in BRANCHES.items():
            try:
                await bot.send_message(chat_id=info['id'], text=order_text)
                logger.info(f"✅ {name}")
            except Exception as e:
                logger.error(f"❌ {name}: {e}")
    else:
        florist_id = BRANCHES[branch]['id']
        try:
            await bot.send_message(chat_id=florist_id, text=order_text)
            logger.info(f"✅ {branch}")
        except Exception as e:
            logger.error(f"❌ {branch}: {e}")

# ============================================
# ЕЖЕДНЕВНАЯ ПРОВЕРКА ДНЕЙ РОЖДЕНИЯ
# ============================================
async def check_birthdays():
    """Проверяет дни рождения за 3 дня вперёд"""
    today = datetime.now()
    target_date = (today + timedelta(days=3)).strftime('%m-%d')
    
    birthdays = db.get_birthdays_by_date(target_date)
    
    for bday in birthdays:
        user_id = bday['user_id']
        recipient = bday['recipient_name']
        
        text = (
            f"🌸 **Через 3 дня день рождения {recipient}!**\n\n"
            f"Мы помним об этом ❤️\n\n"
            f"В честь этого события для вас **персональная скидка 10%** на любой букет!"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Выбрать букет", callback_data="catalog_start")]
        ])
        
        try:
            await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode='Markdown')
            logger.info(f"✅ Напоминание отправлено пользователю {user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки напоминания: {e}")

# ============================================
# ПЛАНИРОВЩИК
# ============================================
async def scheduler():
    while True:
        await asyncio.sleep(3600)  # каждый час
        await check_birthdays()

# ============================================
# ЗАПУСК
# ============================================
async def main():
    asyncio.create_task(run_web_server())
    asyncio.create_task(scheduler())
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Вебхук сброшен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
