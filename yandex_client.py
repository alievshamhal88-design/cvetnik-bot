import requests
import logging
import os
from typing import Optional, Tuple
from io import BytesIO
from PIL import Image
import base64

logger = logging.getLogger(__name__)

class YandexGPTClient:
    def __init__(self):
        self.folder_id = os.getenv("YANDEX_FOLDER_ID")
        self.api_key = os.getenv("YANDEX_API_KEY")
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        
        if not self.folder_id or not self.api_key:
            raise ValueError("❌ Отсутствуют YANDEX_FOLDER_ID или YANDEX_API_KEY")
        
        logger.info(f"✅ YandexGPT клиент инициализирован")

    def generate_test(self) -> Optional[str]:
        """Тестовый запрос"""
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
            return None
        except Exception as e:
            logger.error(f"Ошибка теста: {e}")
            return None

    def generate_bouquet_info(self, image_bytes: bytes) -> Optional[Tuple[str, str]]:
        """Генерирует название и описание букета по фото"""
        try:
            # Подготавливаем изображение
            image = Image.open(BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode()

            headers = {
                "Authorization": f"Api-Key {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.7,
                    "maxTokens": "500"
                },
                "messages": [
                    {
                        "role": "user",
                        "text": (
                            "Посмотри на это фото букета цветов. Напиши для него:\n\n"
                            "1. КРАСИВОЕ НАЗВАНИЕ (2-4 слова, поэтичное, на русском)\n"
                            "2. КОРОТКОЕ ОПИСАНИЕ (2-3 предложения о букете)\n\n"
                            "Формат ответа:\n"
                            "Название: ...\n"
                            "Описание: ..."
                        ),
                        "image": image_base64
                    }
                ]
            }
            
            response = requests.post(self.api_url, headers=headers, json=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                text = result['result']['alternatives'][0]['message']['text']
                
                lines = text.split('\n')
                name = "Волшебный букет"
                description = "Нежный букет для особенного случая."

                for line in lines:
                    if 'Название:' in line:
                        name = line.replace('Название:', '').strip()
                    elif 'Описание:' in line:
                        description = line.replace('Описание:', '').strip()

                return name, description
            return None

        except Exception as e:
            logger.error(f"Ошибка генерации: {e}")
            return None
