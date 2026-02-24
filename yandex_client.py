import requests
import json
import logging
import base64
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image

logger = logging.getLogger(__name__)

class YandexGPTClient:
    def __init__(self, folder_id: str, api_key: str):
        """
        Инициализация клиента YandexGPT
        :param folder_id: ID каталога в Yandex Cloud
        :param api_key: API-ключ сервисного аккаунта
        """
        self.folder_id = folder_id
        self.api_key = api_key
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        logger.info(f"✅ YandexGPT клиент инициализирован (folder_id: {folder_id})")

    def _prepare_image(self, image_bytes: bytes) -> str:
        """
        Подготавливает изображение для отправки в YandexGPT
        """
        # Открываем изображение и конвертируем в JPEG
        image = Image.open(BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Сохраняем в буфер
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        buffer.seek(0)

        # Кодируем в base64
        return base64.b64encode(buffer.read()).decode()

    def generate_bouquet_info(self, image_bytes: bytes) -> Optional[Tuple[str, str]]:
        """
        Генерирует название и описание букета по фото
        Возвращает кортеж (название, описание)
        """
        try:
            # Подготавливаем изображение
            image_base64 = self._prepare_image(image_bytes)

            # Формируем промпт для YandexGPT
            prompt = (
                "Посмотри на это фото букета цветов. Напиши для него:\n\n"
                "1. КРАСИВОЕ НАЗВАНИЕ (2-4 слова, поэтичное, на русском)\n"
                "2. КОРОТКОЕ ОПИСАНИЕ (2-3 предложения о букете: какие цветы, "
                "какое настроение, для какого повода подойдёт)\n\n"
                "Формат ответа (строго соблюдай):\n"
                "Название: ...\n"
                "Описание: ..."
            )

            # Формируем запрос к YandexGPT с правильным форматом для изображений
            payload = {
                "modelUri": f"gpt://{self.folder_id}/yandexgpt/latest",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.7,
                    "maxTokens": "500"
                },
                "messages": [
                    {
                        "role": "user",
                        "text": prompt,
                        "images": [image_base64]  # Изображение передаётся отдельным полем
                    }
                ]
            }

            headers = {
                "Authorization": f"Api-Key {self.api_key}",
                "Content-Type": "application/json"
            }

            logger.info("🔄 Отправляю запрос к YandexGPT...")
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60
            )

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
            logger.error(f"❌ Исключение при работе с YandexGPT: {e}")
            return None

    def generate_test(self) -> Optional[str]:
        """
        Тестовый запрос без изображения
        """
        try:
            payload = {
                "modelUri": f"gpt://{self.folder_id}/yandexgpt/latest",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.7,
                    "maxTokens": "100"
                },
                "messages": [
                    {
                        "role": "user",
                        "text": "Придумай красивое название для букета цветов (только название, без описания)"
                    }
                ]
            }

            headers = {
                "Authorization": f"Api-Key {self.api_key}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return result['result']['alternatives'][0]['message']['text']
            else:
                logger.error(f"❌ Ошибка теста: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка теста: {e}")
            return None
