import os

# ID администраторов
ADMIN_IDS = [
    7651760894,  # @cvetnik1_sib
    7750251679,  # @Alan_Aliev
]

# Настройки Yandex Cloud
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
    raise ValueError("❌ Не найдены YANDEX_FOLDER_ID или YANDEX_API_KEY в переменных окружения!")

# Модели YandexGPT (в порядке предпочтения)
YANDEX_MODELS = [
    "yandexgpt/latest",
    "yandexgpt/rc",
    "yandexgpt/3"
]
