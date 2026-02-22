import logging
import os
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from aiogram import F
from aiohttp import web  # Добавлено для пинг-сервера

# Настройки бота
API_TOKEN = "8462470094:AAHSlSA20IvbGG2AMOBDL9qk3eqXakzuwWg"

# ID филиалов
BRANCHES = {
    '2-я Марата, 22': {'id': 7364255009, 'username': '@cvetnik_sib', 'is_admin': False},
    'Некрасова, 41': {'id': 7651760894, 'username': '@cvetnik1_sib', 'is_admin': True},  # ✅ администратор
    'Связистов, 113А': {'id': 8575692209, 'username': '@cvetniksvezistrov', 'is_admin': False}
}

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Состояния пользователя
STATE_IDLE = 0
STATE_WAITING_PRODUCT = 1   # Ждем выбор букета
STATE_WAITING_CLIENT_NAME = 2  # Ждем имя клиента
STATE_WAITING_CLIENT_PHONE = 3  # Ждем телефон клиента
STATE_WAITING_ADDRESS = 4    # Ждем адрес
STATE_WAITING_RECIPIENT_NAME = 5  # Ждем имя получателя
STATE_WAITING_RECIPIENT_PHONE = 6 # Ждем телефон получателя
STATE_WAITING_RECIPIENT_PHONE_INPUT = 9 # Ждем ввод другого номера
STATE_WAITING_CARD_TEXT = 7  # Ждем текст открытки
STATE_WAITING_BRANCH = 8     # Ждем выбор филиала

user_data = {}
user_states = {}

# Клавиатура для отправки номера телефона (клиента)
client_phone_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Клавиатура для отправки номера получателя
recipient_phone_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Такой же, как у клиента")],
        [KeyboardButton(text="✏️ Ввести другой номер")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Клавиатура для пропуска открытки
card_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 Написать текст")],
        [KeyboardButton(text="⏭️ Без открытки")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Клавиатура выбора филиала
branch_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏢 2-я Марата, 22")],
        [KeyboardButton(text="🏢 Некрасова, 41")],
        [KeyboardButton(text="🏢 Связистов, 113А")],
        [KeyboardButton(text="🚚 Доставка")]
    ],
    resize_keyboard=True
)

# Главное меню
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛒 Оформить заказ")],
        [KeyboardButton(text="📞 Связаться с флористом")],
        [KeyboardButton(text="ℹ️ О нас")]
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_IDLE
    welcome_text = (
        "🌸 Добро пожаловать в «Цветник»!\n\n"
        "Я помогу быстро заказать букет с доставкой по Новосибирску.\n\n"
        "👇 Выберите действие в меню ниже"
    )
    await message.answer(welcome_text, reply_markup=main_keyboard)

@dp.message(F.text == "🛒 Оформить заказ")
async def order_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_WAITING_PRODUCT
    user_data[user_id] = {}
    
    # Кнопка с обычной ссылкой (не WebApp)
    catalog_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🌸 Открыть каталог на сайте",
            url="https://cvetniknsk.ru"
        )]
    ])
    
    await message.answer(
        "🌸 **Выберите букет** одним из способов:\n\n"
        "📸 **Пришлите фото** понравившегося букета\n"
        "📝 **Напишите название** или описание\n"
        "📱 **Фото и названия букетов** вы можете посмотреть на нашем сайте по кнопке ниже",
        reply_markup=catalog_keyboard,
        parse_mode='Markdown'
    )

@dp.message(F.text == "📞 Связаться с флористом")
async def contact_florist(message: types.Message):
    await message.answer(
        "📞 **Контакты наших филиалов:**\n\n"
        "🏢 **Некрасова, 41**\n"
        "📱 +7‒995‒390‒23‒55\n\n"
        "🏢 **2-я улица Марата, 22**\n"
        "📱 +7‒995‒390‒12‒02\n\n"
        "🏢 **Улица Связистов, 113а**\n"
        "📱 +7‒993‒952‒23‒55\n\n"
        "📧 Email: cvetniknsk@yandex.ru",
        parse_mode='Markdown',
        reply_markup=main_keyboard
    )

@dp.message(F.text == "ℹ️ О нас")
async def about(message: types.Message):
    await message.answer(
        "🌸 **«Цветник»** — сеть студий цветов в Новосибирске\n\n"
        "📍 **Наши адреса:**\n"
        "• 2-я Марата, 22\n"
        "• Некрасова, 41\n"
        "• Связистов, 113А\n\n"
        "📞 **Телефон:** +7‒995‒390‒23‒55\n\n"
        "🕒 **Работаем ежедневно** с 9:00 до 22:00\n"
        "🚚 **Доставка** по городу от 500₽\n\n"
        "📍 **Мы на 2ГИС:** [Открыть в 2ГИС](https://2gis.ru/novosibirsk/branches/70000001091590889)",
        parse_mode='Markdown',
        reply_markup=main_keyboard,
        disable_web_page_preview=True
    )

# Обработка фото
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    
    if user_states.get(user_id) != STATE_WAITING_PRODUCT:
        return
    
    # Получаем file_id фото
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # Сохраняем информацию о букете
    user_data[user_id]['product'] = "Фото букета"
    user_data[user_id]['photo'] = file_id
    user_data[user_id]['product_source'] = 'photo'
    
    # Переходим к запросу имени клиента
    user_states[user_id] = STATE_WAITING_CLIENT_NAME
    
    await message.answer(
        "✅ Фото получено!\n\n"
        "📝 Напишите ваше имя:"
    )

# Обработка текста (название букета и все остальные поля)
@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    # Сначала проверяем, не нажата ли одна из главных кнопок
    if text == "🛒 Оформить заказ":
        await order_start(message)
        return
    elif text == "📞 Связаться с флористом":
        await contact_florist(message)
        return
    elif text == "ℹ️ О нас":
        await about(message)
        return
    
    # Проверяем, что мы в состоянии ожидания выбора букета
    if user_states.get(user_id) == STATE_WAITING_PRODUCT:
        # Сохраняем текст как название букета
        user_data[user_id]['product'] = text
        user_data[user_id]['product_source'] = 'text'
        
        # Переходим к запросу имени клиента
        user_states[user_id] = STATE_WAITING_CLIENT_NAME
        
        await message.answer(
            f"✅ Вы выбрали: {text}\n\n"
            f"📝 Напишите ваше имя:"
        )
        return
    
    # Обработка имени клиента
    if user_states.get(user_id) == STATE_WAITING_CLIENT_NAME:
        user_data[user_id]['client_name'] = text
        user_states[user_id] = STATE_WAITING_CLIENT_PHONE
        
        await message.answer(
            f"✅ Имя записано: {text}\n\n"
            f"📱 Отправьте ваш номер телефона для начисления бонусов:",
            reply_markup=client_phone_keyboard
        )
        return
    
    # Обработка адреса
    if user_states.get(user_id) == STATE_WAITING_ADDRESS:
        user_data[user_id]['address'] = text
        user_states[user_id] = STATE_WAITING_RECIPIENT_NAME
        
        await message.answer(
            "✅ Адрес записан.\n\n"
            "👤 Напишите имя получателя:",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # Обработка имени получателя
    if user_states.get(user_id) == STATE_WAITING_RECIPIENT_NAME:
        user_data[user_id]['recipient_name'] = text
        user_states[user_id] = STATE_WAITING_RECIPIENT_PHONE
        
        await message.answer(
            f"✅ Имя получателя: {text}\n\n"
            f"📱 Выберите вариант для телефона получателя:",
            reply_markup=recipient_phone_keyboard
        )
        return
    
    # Обработка телефона получателя
    if user_states.get(user_id) == STATE_WAITING_RECIPIENT_PHONE:
        if text == "📱 Такой же, как у клиента":
            user_data[user_id]['recipient_phone'] = user_data[user_id]['client_phone']
            user_states[user_id] = STATE_WAITING_CARD_TEXT
            await message.answer(
                "✅ Телефон получателя совпадает с вашим.\n\n"
                "💌 Напишите текст для открытки (или пропустите):",
                reply_markup=card_keyboard
            )
        elif text == "✏️ Ввести другой номер":
            user_states[user_id] = STATE_WAITING_RECIPIENT_PHONE_INPUT
            await message.answer(
                "📱 Введите номер телефона получателя:",
                reply_markup=ReplyKeyboardRemove()
            )
        return
    
    # Обработка ввода другого номера получателя
    if user_states.get(user_id) == STATE_WAITING_RECIPIENT_PHONE_INPUT:
        user_data[user_id]['recipient_phone'] = text
        user_states[user_id] = STATE_WAITING_CARD_TEXT
        await message.answer(
            f"✅ Телефон получателя: {text}\n\n"
            f"💌 Напишите текст для открытки (или пропустите):",
            reply_markup=card_keyboard
        )
        return
    
    # Обработка текста открытки
    if user_states.get(user_id) == STATE_WAITING_CARD_TEXT:
        if text == "⏭️ Без открытки":
            user_data[user_id]['card_text'] = "Без открытки"
        else:
            user_data[user_id]['card_text'] = text
        
        user_states[user_id] = STATE_WAITING_BRANCH
        
        await message.answer(
            "✅ Данные открытки сохранены.\n\n"
            "📍 Выберите удобный филиал для самовывоза или оформите доставку:",
            reply_markup=branch_keyboard
        )
        return
    
    # Обработка выбора филиала
    elif user_states.get(user_id) == STATE_WAITING_BRANCH:
        branch_map = {
            "🏢 2-я Марата, 22": "2-я Марата, 22",
            "🏢 Некрасова, 41": "Некрасова, 41",
            "🏢 Связистов, 113А": "Связистов, 113А",
            "🚚 Доставка": "доставка"
        }
        
        if text in branch_map:
            user_data[user_id]['branch'] = branch_map[text]
            
            # Отправляем заказ флористу
            await send_order_to_florist(message, user_id)
            
            # Подтверждение клиенту
            branch_text = "доставка" if user_data[user_id]['branch'] == "доставка" else f"филиал {user_data[user_id]['branch']}"
            
            await message.answer(
                f"✅ **ЗАКАЗ ПРИНЯТ!**\n\n"
                f"🌸 Букет: {user_data[user_id]['product']}\n"
                f"👤 Получатель: {user_data[user_id]['recipient_name']}\n"
                f"📍 Адрес: {user_data[user_id]['address']}\n"
                f"🏢 {branch_text}\n"
                f"💌 Открытка: {user_data[user_id].get('card_text', 'Без открытки')}\n\n"
                f"Флорист начал сборку. Ожидайте подтверждения!",
                parse_mode='Markdown',
                reply_markup=main_keyboard
            )
            
            user_states[user_id] = STATE_IDLE
        else:
            await message.answer("Пожалуйста, выберите вариант из меню:")
        return

# Обработка контакта (телефон клиента)
@dp.message(F.contact)
async def handle_client_phone(message: types.Message):
    user_id = message.from_user.id
    
    if user_states.get(user_id) != STATE_WAITING_CLIENT_PHONE:
        return
    
    # Сохраняем номер телефона клиента
    user_data[user_id]['client_phone'] = message.contact.phone_number
    user_states[user_id] = STATE_WAITING_ADDRESS
    
    await message.answer(
        "✅ Номер получен!\n\n"
        "📝 Напишите адрес доставки и желаемое время:\n"
        "Например: ул. Некрасова, 41, кв. 5, сегодня к 18:00",
        reply_markup=ReplyKeyboardRemove()
    )

async def send_order_to_florist(message: types.Message, user_id: int):
    client_name = user_data[user_id].get('client_name', 'Не указано')
    username = message.from_user.username or "Нет username"
    
    # Формируем информацию о букете
    product_info = user_data[user_id]['product']
    if user_data[user_id].get('product_source') == 'photo':
        product_info = "📸 [Фото букета]"
    
    order_text = (
        f"🌸 НОВЫЙ ЗАКАЗ 🌸\n\n"
        f"👤 Клиент: {client_name}\n"
        f"📱 Телефон клиента: {user_data[user_id]['client_phone']}\n"
        f"👤 Получатель: {user_data[user_id].get('recipient_name', 'Не указано')}\n"
        f"📱 Телефон получателя: {user_data[user_id].get('recipient_phone', 'Не указано')}\n"
        f"📍 Адрес: {user_data[user_id]['address']}\n"
        f"🌸 Букет: {product_info}\n"
    )
    
    # Добавляем цену, если есть
    if user_data[user_id].get('price'):
        order_text += f"💰 Цена: {user_data[user_id]['price']} ₽\n"
    
    # Добавляем текст открытки
    if user_data[user_id].get('card_text'):
        order_text += f"💌 Открытка: {user_data[user_id]['card_text']}\n"
    
    order_text += (
        f"🏢 Филиал: {user_data[user_id]['branch']}\n"
        f"🆔 Username: @{username}\n\n"
        f"⚡️ Приступайте к сборке!"
    )
    
    branch = user_data[user_id]['branch']
    
    # Всегда отправляем администратору (7651760894)
    admin_id = 7651760894
    try:
        await bot.send_message(
            chat_id=admin_id,
            text=order_text
        )
        if user_data[user_id].get('photo'):
            await bot.send_photo(
                chat_id=admin_id,
                photo=user_data[user_id]['photo'],
                caption="📸 Фото букета к заказу выше"
            )
        logging.info(f"✅ Заказ отправлен администратору {admin_id}")
    except Exception as e:
        logging.error(f"❌ Ошибка отправки администратору: {e}")
        logging.error(f"   Возможно, администратор не запускал бота. Попросите @cvetnik1_sib написать /start")
    
    # Отправляем в конкретный филиал (если выбран)
    if branch != "доставка":
        florist_id = BRANCHES[branch]['id']
        try:
            await bot.send_message(
                chat_id=florist_id,
                text=order_text
            )
            if user_data[user_id].get('photo'):
                await bot.send_photo(
                    chat_id=florist_id,
                    photo=user_data[user_id]['photo'],
                    caption="📸 Фото букета к заказу выше"
                )
            logging.info(f"✅ Заказ отправлен в филиал {branch}")
        except Exception as e:
            logging.error(f"❌ Ошибка отправки в {branch}: {e}")
    else:
        # При доставке отправляем всем филиалам
        for branch_name, branch_info in BRANCHES.items():
            try:
                await bot.send_message(
                    chat_id=branch_info['id'],
                    text=order_text
                )
                if user_data[user_id].get('photo'):
                    await bot.send_photo(
                        chat_id=branch_info['id'],
                        photo=user_data[user_id]['photo'],
                        caption="📸 Фото букета к заказу выше"
                    )
                logging.info(f"✅ Заказ отправлен в {branch_name}")
            except Exception as e:
                logging.error(f"❌ Ошибка отправки в {branch_name}: {e}")

# ---------- ПИНГ-СЕРВЕР ДЛЯ RENDER ----------
async def handle_ping(request):
    """Обработчик для пинг-запросов от UptimeRobot"""
    return web.Response(text='OK')

async def run_web_server():
    """Запуск простого веб-сервера для пинга"""
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/ping', handle_ping)
    
    # Render сам назначает порт через переменную окружения PORT
    port = int(os.environ.get('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Пинг-сервер запущен на порту {port}")

# ИСПРАВЛЕННАЯ ФУНКЦИЯ MAIN
async def main():
    # Запускаем веб-сервер для пинга в фоне
    asyncio.create_task(run_web_server())
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
