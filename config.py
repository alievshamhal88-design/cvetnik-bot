import os

# ID администраторов (кто может загружать фото в каталог)
# Здесь только ваш личный ID
ADMIN_IDS = [
    7750251679,  # @Alan_Aliev
]

# Модели YandexGPT (если ещё используете)
YANDEX_MODELS = [
    "yandexgpt/latest",
    "yandexgpt/rc",
    "yandexgpt/3"
]

# Yandex Cloud AI (если используете)
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
