import os

# ID администраторов
ADMIN_IDS = [
    7651760894,  # @cvetnik1_sib
    7750251679,  # @Alan_Aliev
]

# Проверка наличия переменных окружения (необязательно, можно оставить как есть)
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

# Модели YandexGPT (можно оставить для fallback, но в новом клиенте не используются)
YANDEX_MODELS = [
    "yandexgpt/latest",
    "yandexgpt/rc",
    "yandexgpt/3"
]
