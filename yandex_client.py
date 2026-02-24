import requests
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

class YandexGPTClient:
    def __init__(self):
        """Инициализация клиента YandexGPT"""
        self.folder_id = os.getenv("YANDEX_FOLDER_ID")
        self.api_key = os.getenv("YANDEX_API_KEY")
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        
        if not self.folder_id or not self.api_key:
            raise ValueError("❌ Отсутствуют YANDEX_FOLDER_ID или YANDEX_API_KEY")
        
        logger.info("✅ YandexGPT клиент инициализирован")

    def generate_bouquet_name(self) -> Optional[str]:
        """
        Генерирует случайное милое название для букета
        """
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Разные варианты промптов для разнообразия
        prompts = [
            "Придумай красивое название для букета цветов. Название должно быть нежным, поэтичным, на русском языке. Только само название, 2-4 слова.",
            "Придумай романтическое название для букета цветов. Название должно быть милым и вдохновляющим. Только название, 2-4 слова.",
            "Придумай весеннее название для букета цветов. Пусть оно звучит нежно и свежо. Только название, 2-4 слова."
        ]
        
        # Случайный выбор промпта
        import random
        prompt = random.choice(prompts)
        
        data = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite",
            "completionOptions": {
                "stream": False,
                "temperature": 0.9,  # Чем выше, тем разнообразнее
                "maxTokens": "50"
            },
            "messages": [
                {
                    "role": "user",
                    "text": prompt
                }
            ]
        }
        
        try:
            logger.info("🔄 Генерирую название букета...")
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                name = result['result']['alternatives'][0]['message']['text'].strip()
                # Очищаем от кавычек и лишних символов
                name = name.strip('"').strip("'").strip('«').strip('»').strip()
                logger.info(f"✅ Сгенерировано название: {name}")
                return name
            else:
                logger.error(f"❌ Ошибка YandexGPT: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации: {e}")
            return None

    def generate_test(self) -> Optional[str]:
        """Простой тест для проверки"""
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite",
            "completionOptions": {
                "stream": False,
                "temperature": 0.6,
                "maxTokens": "50"
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
