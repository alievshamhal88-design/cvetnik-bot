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
from gigachat_client import GigaChatClient

# ============================================
# НАСТРОЙКИ БОТА
# ============================================
API_TOKEN = "8462470094:AAHSlSA20IvbGG2AMOBDL9qk3eqXakzuwWg"

# GigaChat авторизация
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")

if GIGACHAT_AUTH_KEY:
    gigachat = GigaChatClient(auth_key=GIGACHAT_AUTH_KEY)
elif GIGACHAT_CLIENT_ID and GIGACHAT_CLIENT_SECRET:
    gigachat = GigaChatClient(
        client_id=GIGACHAT_CLIENT_ID,
        client_secret=GIGACHAT_CLIENT_SECRET
    )
else:
    raise ValueError("❌ Не найдены авторизационные данные для GigaChat!")

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
# КЛАВИАТУРЫ (без изменений)
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
# ФУНКЦИИ ДЛЯ GIGACHAT
# ============================================
async def generate_bouquet_info(photo_file_id):
    """
    GigaChat смотрит на фото и генерирует название и описание
    """
    try:
        # Скачиваем фото
        file_info = await bot.get_file(photo_file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        image_bytes = file_bytes.read()
        
        # Генерируем через GigaChat
        result = gigachat.generate_with_image(
            prompt="",
            image_bytes=image_bytes,
            model='GigaChat-2-Max'
        )
        
        if result:
            name, description = result
            logger.info(f"✅ GigaChat: {name}")
            return name, description
        
    except Exception as e:
        logger.error(f"❌ Ошибка GigaChat: {e}")
    
    # Запасные варианты
    fallback_names = ["Нежность утра", "Цветочная симфония", "Весеннее настроение"]
    fallback_desc = ["Нежный букет из свежих цветов, собранный с любовью."]
    return random.choice(fallback_names), random.choice(fallback_desc)

# ============================================
# ОБРАБОТЧИКИ
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

@dp.message(Command("test_gigachat"))
async def test_gigachat(message: types.Message):
    """Тест GigaChat без фото"""
    try:
        result = gigachat.generate_with_image(
            prompt="Придумай красивое название для букета цветов",
            image_bytes=None,
            model='GigaChat-2-Lite'
        )
        if result:
            name, desc = result
            await message.answer(f"✅ GigaChat ответил:\nНазвание: {name}\nОписание: {desc}")
        else:
            await message.answer("❌ GigaChat не ответил")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

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
    user_id = message.from_user.id
    
    if db.get_bouquets_count() == 0:
        await message.answer("😢 В каталоге пока нет букетов. Скоро добавим!")
        return
    
    for i in range(3):
        bouquet = db.get_random_bouquet()
        if not bouquet:
            continue
        
        status_msg = await message.answer(f"🌸 Подбираем для вас лучший букет... ✨")
        name, description = await generate_bouquet_info(bouquet['photo_file_id'])
        await status_msg.delete()
        
        user_data[user_id] = user_data.get(user_id, {})
        user_data[user_id][f'b_name_{i}'] = name
        user_data[user_id][f'b_desc_{i}'] = description
        user_data[user_id][f'b_id_{i}'] = bouquet['id']
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выбрать этот букет", callback_data=f"select_{i}")]
        ])
        
        caption = f"🌸 **{name}**\n\n{description}"
        await message.answer_photo(
            photo=bouquet['photo_file_id'],
            caption=caption,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

@dp.callback_query(F.data.startswith('select_'))
async def select_bouquet(callback: types.CallbackQuery):
    index = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    
    name = user_data.get(user_id, {}).get(f'b_name_{index}', "Выбранный букет")
    desc = user_data.get(user_id, {}).get(f'b_desc_{index}', "")
    
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]['product'] = name
    user_data[user_id]['product_description'] = desc
    user_data[user_id]['product_source'] = 'catalog_ai'
    
    await callback.message.answer(
        f"✅ Вы выбрали: **{name}**\n\n📝 Теперь напишите ваше имя:",
        parse_mode='Markdown'
    )
    user_states[user_id] = STATE_WAITING_CLIENT_NAME
    await callback.answer()

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
        "🏢 **Некрасова, 41**\n📱 +7‒995‒390‒23‒55\n\n"
        "🏢 **2-я улица Марата, 22**\n📱 +7‒995‒390‒12‒02\n\n"
        "🏢 **Улица Связистов, 113а**\n📱 +7‒993‒952‒23‒55\n\n"
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
# ОФОРМЛЕНИЕ ЗАКАЗА
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

# ============================================
# ОБРАБОТКА ТЕКСТА
# ============================================
@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    if text in ["🛒 Оформить заказ", "🌸 Выбрать букет из каталога", 
                "🎂 Сохранить день рождения", "📦 Цветочная подписка",
                "📞 Связаться с флористом", "ℹ️ О нас"]:
        return
    
    state = user_states.get(user_id)
    
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
    
    # Обработка дня рождения
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
# ЗАПУСК
# ============================================
async def main():
    asyncio.create_task(run_web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Вебхук сброшен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
