import requests
import logging

logger = logging.getLogger(__name__)

class YandexGPTClient:
    def __init__(self, folder_id: str, api_key: str):
        self.folder_id = folder_id
        self.api_key = api_key
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        logger.info("✅ Клиент инициализирован")

    def generate_test(self) -> str | None:
        """Предельно простой тестовый запрос"""
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite",
            "completionOptions": {
                "stream": False,
                "temperature": 0.6,
                "maxTokens": "200"
            },
            "messages": [
                {
                    "role": "user",
                    "text": "Скажи 'Привет, бот работает' по-русски"
                }
            ]
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result['result']['alternatives'][0]['message']['text']
            else:
                logger.error(f"Ошибка {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Исключение: {e}")
            return None
