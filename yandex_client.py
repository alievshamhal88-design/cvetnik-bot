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
        """Инициализация клиента YandexGPT с данными из переменных окружения"""
        self.folder_id = os.getenv("YANDEX_FOLDER_ID")
        self.api_key = os.getenv("YANDEX_API_KEY")
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        
        if not self.folder_id or not self.api_key:
            raise ValueError("❌ Отсутствуют YANDEX_FOLDER_ID или YANDEX_API_KEY в переменных окружения!")
        
        logger.info(f"✅ YandexGPT клиент инициализирован с Folder ID: {self.folder_id}")

    def generate_test(self) -> Optional[str]:
        """Простой тестовый запрос без изображения"""
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
            logger.info("🔄 Отправляю тестовый запрос к YandexGPT...")
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                answer = result['result']['alternatives'][0]['message']['text']
                logger.info(f"✅ YandexGPT ответил: {answer}")
                return answer
            else:
                logger.error(f"❌ Ошибка {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"❌ Исключение: {e}")
            return None

    def _prepare_image(self, image_bytes: bytes) -> str:
        """Подготавливает изображение для отправки"""
        try:
            image = Image.open(BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)
            return base64.b64encode(buffer.read()).decode()
        except Exception as e:
            logger.error(f"❌ Ошибка подготовки изображения: {e}")
            return None

    def generate_bouquet_info(self, image_bytes: bytes) -> Optional[Tuple[str, str]]:
        """Генерирует название и описание букета по фото"""
        try:
            # Подготавливаем изображение
            image_base64 = self._prepare_image(image_bytes)
            if not image_base64:
                return None

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
                            "2. КОРОТКОЕ ОПИСАНИЕ (2-3 предложения о букете: какие цветы, "
                            "какое настроение, для какого повода подойдёт)\n\n"
                            "Формат ответа (строго соблюдай):\n"
                            "Название: ...\n"
                            "Описание: ..."
                        ),
                        "image": image_base64
                    }
                ]
            }
            
            logger.info("🔄 Отправляю запрос с изображением к YandexGPT...")
            response = requests.post(self.api_url, headers=headers, json=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                text = result['result']['alternatives'][0]['message']['text']
                
                # Парсим ответ
                lines = text.split('\n')
                name = "Волшебный букет"
                description = "Нежный букет для особенного случая."

                for line in lines:
                    if 'Название:' in line:
                        name = line.replace('Название:', '').strip()
                    elif 'Описание:' in line:
                        description = line.replace('Описание:', '').strip()

                logger.info(f"✅ YandexGPT сгенерировал: {name}")
                return name, description
            else:
                logger.error(f"❌ Ошибка YandexGPT: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"❌ Исключение: {e}")
            return None
