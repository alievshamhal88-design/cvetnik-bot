import logging
import os
import json
import asyncio
import signal
import time
from datetime import datetime, timedelta
from functools import wraps
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

from config import ADMIN_IDS, POST_TIMES
from database import Database

# ============================================
# НАСТРОЙКИ БОТА
# ============================================
API_TOKEN = "8462470094:AAHSlSA20IvbGG2AMOBDL9qk3eqXakzuwWg"

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
# ТЕСТОВЫЙ ОБРАБОТЧИК (ВРЕМЕННО)
# ============================================
@dp.message(Command("test"))
async def test_handler(message: types.Message):
    await message.answer(f"✅ Тест работает! Ваш ID: {message.from_user.id}")

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

# НОВЫЕ СОСТОЯНИЯ
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

# ОБНОВЛЁННОЕ ГЛАВНОЕ МЕНЮ
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
# МОДУЛЬ 1: ПОДБОР ПО ФОТО
# ============================================
@dp.message(F.text == "🌸 Выбрать букет из каталога")
async def catalog_start(message: types.Message):
    bouquets = []
    for _ in range(3):
        b = db.get_random_bouquet()
        if b:
            bouquets.append(b)
    
    if not bouquets:
        await message.answer("😢 В каталоге пока нет букетов. Флорист скоро их добавит!")
        return
    
    for b in bouquets:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выбрать этот букет", callback_data=f"select_{b['id']}")]
        ])
        
        caption = f"🌸 {b['name'] or 'Букет'}\n"
        if b.get('price'):
            caption += f"💰 Цена: {b['price']} ₽\n"
        if b.get('description'):
            caption += f"📝 {b['description']}"
        
        await message.answer_photo(
            photo=b['photo_file_id'],
            caption=caption,
            reply_markup=keyboard
        )

@dp.callback_query(F.data.startswith('select_'))
async def select_bouquet(callback: types.CallbackQuery):
    bouquet_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]['selected_bouquet_id'] = bouquet_id
    user_data[user_id]['product_source'] = 'catalog'
    
    await callback.message.answer(
        "✅ Букет выбран! Теперь продолжим оформление заказа.\n\n"
        "📝 Напишите ваше имя:"
    )
    user_states[user_id] = STATE_WAITING_CLIENT_NAME
    await callback.answer()

# ============================================
# МОДУЛЬ 2: ДНИ РОЖДЕНИЯ
# ============================================
@dp.message(F.text == "🎂 Сохранить день рождения")
async def birthday_start(message: types.Message):
    await message.answer(
        "🎂 **Сохраним день рождения вашего близкого!**\n\n"
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
# МОДУЛЬ 3: ПОДПИСКА
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
        "**Варианты:**\n"
        "• **С напоминанием** — я напомню, вы подтвердите\n"
        "• **Автоматическая** — заказ оформляется сам, деньги списываются\n\n"
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
        "**Шаг 1 из 6**\n"
        "Кому вы хотите отправлять цветы? Введите имя получателя:"
    )
    await callback.answer()

@dp.callback_query(F.data == "sub_info")
async def subscription_info(callback: types.CallbackQuery):
    text = (
        "🌸 **Как работает подписка**\n\n"
        "1. Вы указываете получателя и бюджет\n"
        "2. Выбираете частоту (раз в неделю/месяц)\n"
        "3. Выбираете режим:\n"
        "   • **С напоминанием** — я пришлю уведомление, вы подтвердите\n"
        "   • **Автоматическая** — заказ оформляется сам\n"
        "4. В указанный день я создаю заказ и передаю флористу\n\n"
        "Управлять подписками можно в разделе «Мои подписки»"
    )
    await callback.message.answer(text)
    await callback.answer()

# ============================================
# ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (КОМАНДЫ)
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_IDLE
    user_data[user_id] = {}
    
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('product_'):
        parts = args[1].split('_')
        product_name = 'Букет'
        if len(parts) >= 3:
            product_name = ' '.join(parts[2:]).replace('%20', ' ')
        
        user_data[user_id]['product'] = product_name
        user_states[user_id] = STATE_WAITING_CLIENT_PHONE
        await message.answer(
            f"✅ Вы выбрали: {product_name}\n\n📱 Теперь отправьте ваш номер телефона:",
            reply_markup=client_phone_keyboard
        )
    else:
        await message.answer(
            "🌸 Добро пожаловать в «Цветник»!\n\n"
            "Я помогу быстро заказать букет с доставкой по Новосибирску.\n\n"
            "👇 Выберите действие в меню ниже",
            reply_markup=main_keyboard
        )

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

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    if user_states.get(user_id) != STATE_WAITING_PRODUCT:
        return
    
    photo = message.photo[-1]
    user_data[user_id]['product'] = "Фото букета"
    user_data[user_id]['photo'] = photo.file_id
    user_data[user_id]['product_source'] = 'photo'
    user_states[user_id] = STATE_WAITING_CLIENT_NAME
    
    await message.answer("✅ Фото получено!\n\n📝 Напишите ваше имя:")

@dp.message(F.contact)
async def handle_client_phone(message: types.Message):
    user_id = message.from_user.id
    if user_states.get(user_id) != STATE_WAITING_CLIENT_PHONE:
        return
    
    user_data[user_id]['client_phone'] = message.contact.phone_number
    user_states[user_id] = STATE_WAITING_ADDRESS
    
    await message.answer(
        "✅ Номер получен!\n\n📝 Напишите адрес доставки и желаемое время:\n"
        "Например: ул. Некрасова, 41, кв. 5, сегодня к 18:00",
        reply_markup=ReplyKeyboardRemove()
    )

# ============================================
# ОБРАБОТКА ТЕКСТА (ЗАКАЗ)
# ============================================
@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    # Проверяем главные кнопки
    if text in ["🛒 Оформить заказ", "🌸 Выбрать букет из каталога", 
                "🎂 Сохранить день рождения", "📦 Цветочная подписка",
                "📞 Связаться с флористом", "ℹ️ О нас"]:
        return
    
    state = user_states.get(user_id)
    
    # Шаги подписки
    if state == STATE_SUB_RECIPIENT:
        user_data[user_id]['sub_recipient'] = text
        user_states[user_id] = STATE_SUB_PHONE
        await message.answer(
            "📞 **Шаг 2 из 6**\n"
            "Введите телефон получателя (или отправьте /skip если не хотите указывать):"
        )
        return
    
    if state == STATE_SUB_PHONE:
        if text != '/skip':
            user_data[user_id]['sub_phone'] = text
        user_states[user_id] = STATE_SUB_ADDRESS
        await message.answer(
            "📍 **Шаг 3 из 6**\n"
            "Введите адрес получателя (или /skip если не хотите указывать):"
        )
        return
    
    if state == STATE_SUB_ADDRESS:
        if text != '/skip':
            user_data[user_id]['sub_address'] = text
        user_states[user_id] = STATE_SUB_FREQUENCY
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Раз в неделю", callback_data="freq_weekly")],
            [InlineKeyboardButton(text="Раз в месяц", callback_data="freq_monthly")],
            [InlineKeyboardButton(text="Каждое 8 число", callback_data="freq_custom")]
        ])
        await message.answer(
            "📅 **Шаг 4 из 6**\n"
            "Как часто отправлять букеты?",
            reply_markup=keyboard
        )
        return
    
    if state == STATE_SUB_BUDGET:
        try:
            budget = int(text.replace('₽', '').replace(' ', ''))
            user_data[user_id]['sub_budget'] = budget
            user_states[user_id] = STATE_SUB_CONFIRM
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ С напоминанием", callback_data="confirm_remind")],
                [InlineKeyboardButton(text="🤖 Автоматическая", callback_data="confirm_auto")]
            ])
            await message.answer(
                "🔄 **Шаг 6 из 6**\n"
                "Выберите режим подписки:",
                reply_markup=keyboard
            )
        except:
            await message.answer("❌ Введите число (например: 3000)")
        return
    
    # Шаги заказа (остальные)
    if state == STATE_WAITING_PRODUCT:
        user_data[user_id]['product'] = text
        user_data[user_id]['product_source'] = 'text'
        user_states[user_id] = STATE_WAITING_CLIENT_NAME
        await message.answer(f"✅ Вы выбрали: {text}\n\n📝 Напишите ваше имя:")
        return
    
    if state == STATE_WAITING_CLIENT_NAME:
        user_data[user_id]['client_name'] = text
        user_states[user_id] = STATE_WAITING_CLIENT_PHONE
        await message.answer(
            f"✅ Имя записано: {text}\n\n📱 Отправьте ваш номер телефона:",
            reply_markup=client_phone_keyboard
        )
        return
    
    if state == STATE_WAITING_ADDRESS:
        user_data[user_id]['address'] = text
        user_states[user_id] = STATE_WAITING_RECIPIENT_NAME
        await message.answer(
            "✅ Адрес записан.\n\n👤 Напишите имя получателя:",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    if state == STATE_WAITING_RECIPIENT_NAME:
        user_data[user_id]['recipient_name'] = text
        user_states[user_id] = STATE_WAITING_RECIPIENT_PHONE
        await message.answer(
            f"✅ Имя получателя: {text}\n\n📱 Выберите вариант для телефона получателя:",
            reply_markup=recipient_phone_keyboard
        )
        return
    
    if state == STATE_WAITING_RECIPIENT_PHONE:
        if text == "📱 Такой же, как у клиента":
            user_data[user_id]['recipient_phone'] = user_data[user_id]['client_phone']
            user_states[user_id] = STATE_WAITING_CARD_TEXT
            await message.answer(
                "✅ Телефон совпадает.\n\n💌 Напишите текст для открытки (или пропустите):",
                reply_markup=card_keyboard
            )
        elif text == "✏️ Ввести другой номер":
            user_states[user_id] = STATE_WAITING_RECIPIENT_PHONE_INPUT
            await message.answer(
                "📱 Введите номер телефона получателя:",
                reply_markup=ReplyKeyboardRemove()
            )
        return
    
    if state == STATE_WAITING_RECIPIENT_PHONE_INPUT:
        user_data[user_id]['recipient_phone'] = text
        user_states[user_id] = STATE_WAITING_CARD_TEXT
        await message.answer(
            f"✅ Телефон получателя: {text}\n\n💌 Напишите текст для открытки (или пропустите):",
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
            "✅ Данные сохранены.\n\n📍 Выберите удобный филиал:",
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
                f"💌 Открытка: {user_data[user_id].get('card_text', 'Без открытки')}\n\n"
                f"Флорист начал сборку.",
                parse_mode='Markdown',
                reply_markup=main_keyboard
            )
            user_states[user_id] = STATE_IDLE
        else:
            await message.answer("Пожалуйста, выберите вариант из меню:")

@dp.callback_query(F.data.startswith('freq_'))
async def subscription_frequency(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    freq = callback.data.split('_')[1]
    
    user_data[user_id]['sub_frequency'] = freq
    user_states[user_id] = STATE_SUB_BUDGET
    
    await callback.message.edit_text(
        "💰 **Шаг 5 из 6**\n"
        "Какой бюджет на один букет? (в рублях)\n"
        "Например: 3000"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith('confirm_'))
async def subscription_confirm(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    mode = callback.data.split('_')[1]
    
    data = user_data.get(user_id, {})
    
    sub_data = {
        'user_id': user_id,
        'recipient_name': data.get('sub_recipient', ''),
        'recipient_phone': data.get('sub_phone', ''),
        'recipient_address': data.get('sub_address', ''),
        'frequency': data.get('sub_frequency', 'monthly'),
        'budget': data.get('sub_budget', 0),
        'auto_confirm': 1 if mode == 'auto' else 0,
        'next_date': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    }
    
    sub_id = db.add_subscription(sub_data)
    
    if sub_id:
        await callback.message.edit_text(
            "✅ **Подписка оформлена!**\n\n"
            f"Получатель: {sub_data['recipient_name']}\n"
            f"Бюджет: {sub_data['budget']} ₽\n"
            f"Режим: {'Автоматический' if mode == 'auto' else 'С напоминанием'}\n\n"
            f"Следующая отправка: примерно {sub_data['next_date']}\n\n"
            "Управлять подпиской можно в разделе «Мои подписки»"
        )
    else:
        await callback.message.edit_text("❌ Ошибка при оформлении подписки")
    
    user_states[user_id] = STATE_IDLE
    await callback.answer()

# ============================================
# ОТПРАВКА ЗАКАЗА ФЛОРИСТАМ
# ============================================
async def send_order_to_florist(message: types.Message, user_id: int):
    client_name = user_data[user_id].get('client_name', 'Не указано')
    username = message.from_user.username or "Нет username"
    
    product_info = user_data[user_id]['product']
    if user_data[user_id].get('product_source') == 'photo':
        product_info = "📸 [Фото букета]"
    
    order_text = (
        f"🌸 НОВЫЙ ЗАКАЗ 🌸\n\n"
        f"👤 Клиент: {client_name}\n"
        f"📱 Телефон: {user_data[user_id]['client_phone']}\n"
        f"👤 Получатель: {user_data[user_id].get('recipient_name', 'Не указано')}\n"
        f"📱 Телефон получателя: {user_data[user_id].get('recipient_phone', 'Не указано')}\n"
        f"📍 Адрес: {user_data[user_id]['address']}\n"
        f"🌸 Букет: {product_info}\n"
    )
    
    if user_data[user_id].get('price'):
        order_text += f"💰 Цена: {user_data[user_id]['price']} ₽\n"
    if user_data[user_id].get('card_text'):
        order_text += f"💌 Открытка: {user_data[user_id]['card_text']}\n"
    
    order_text += f"🏢 Филиал: {user_data[user_id]['branch']}\n🆔 @{username}\n\n⚡️ Собирайте!"

    branch = user_data[user_id]['branch']
    admin_id = 7651760894
    
    # Администратору
    try:
        await bot.send_message(chat_id=admin_id, text=order_text)
        if user_data[user_id].get('photo'):
            await bot.send_photo(chat_id=admin_id, photo=user_data[user_id]['photo'],
                                 caption="📸 Фото букета к заказу")
        logger.info(f"✅ Администратору {admin_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка админу: {e}")

    # Филиалам
    if branch == "доставка":
        for name, info in BRANCHES.items():
            try:
                await bot.send_message(chat_id=info['id'], text=order_text)
                if user_data[user_id].get('photo'):
                    await bot.send_photo(chat_id=info['id'], photo=user_data[user_id]['photo'])
                logger.info(f"✅ {name}")
            except Exception as e:
                logger.error(f"❌ {name}: {e}")
    else:
        florist_id = BRANCHES[branch]['id']
        try:
            await bot.send_message(chat_id=florist_id, text=order_text)
            if user_data[user_id].get('photo'):
                await bot.send_photo(chat_id=florist_id, photo=user_data[user_id]['photo'])
            logger.info(f"✅ {branch}")
        except Exception as e:
            logger.error(f"❌ {branch}: {e}")

# ============================================
# ЕЖЕДНЕВНАЯ ПРОВЕРКА ДНЕЙ РОЖДЕНИЯ
# ============================================
async def check_birthdays():
    today = datetime.now()
    target_date = (today + timedelta(days=3)).strftime('%m-%d')
    
    birthdays = db.get_birthdays_by_date(target_date)
    logger.info(f"🔍 Проверка дней рождения: {target_date}, найдено: {len(birthdays)}")
    
    for bday in birthdays:
        user_id = bday['user_id']
        recipient = bday['recipient_name']
        promo = f"BDAY{bday['id']}10"
        
        text = (
            f"🌸 **Через 3 дня день рождения {recipient}!**\n\n"
            f"Мы помним об этом ❤️\n\n"
            f"В честь этого события для вас **персональная скидка 10%** на любой букет.\n"
            f"Промокод: `{promo}`\n\n"
            f"Скажите этот код флористу при оформлении заказа!"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Выбрать букет", callback_data="start_order")],
            [InlineKeyboardButton(text="⏰ Напомнить позже", callback_data="remind_later")]
        ])
        
        try:
            await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode='Markdown')
            logger.info(f"✅ Напоминание отправлено пользователю {user_id} про {recipient}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки напоминания {user_id}: {e}")

# ============================================
# ПЛАНИРОВЩИК
# ============================================
async def scheduler():
    while True:
        now = datetime.now()
        # Проверяем каждый час
        await asyncio.sleep(3600)
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
