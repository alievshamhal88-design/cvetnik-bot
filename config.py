# ID администраторов
ADMIN_IDS = [
    7651760894,  # @cvetnik1_sib
    7750251679,  # @Alan_Aliev
]

# Модели GigaChat (в порядке предпочтения)
GIGACHAT_MODELS = [
    'GigaChat-2-Max',
    'GigaChat-2-Pro',
    'GigaChat-2-Lite',
    'GigaChat'
]

# Авторизационные данные (будут в переменных окружения)
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")
# Или готовый Authorization Key
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
