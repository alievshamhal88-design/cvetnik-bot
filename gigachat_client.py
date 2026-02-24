import requests
import base64
import json
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class GigaChatClient:
    def __init__(self, client_id=None, client_secret=None, auth_key=None):
        """
        Инициализация клиента GigaChat
        Можно использовать либо пару (client_id, client_secret), либо готовый auth_key
        """
        self.auth_token = None
        self.token_expires = 0
        
        if auth_key:
            self.auth_key = auth_key
        elif client_id and client_secret:
            # Кодируем client_id:client_secret в base64
            credentials = f"{client_id}:{client_secret}"
            self.auth_key = base64.b64encode(credentials.encode()).decode()
        else:
            raise ValueError("❌ Необходимо указать либо auth_key, либо пару client_id:client_secret")
        
        logger.info("✅ GigaChat клиент инициализирован")
    
    def _get_auth_token(self):
        """Получение токена доступа"""
        if self.auth_token and time.time() < self.token_expires:
            return self.auth_token
        
        try:
            headers = {
                'Authorization': f'Basic {self.auth_key}',
                'RqUID': 'cvetnik-bot',  # Уникальный ID запроса
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            data = {'scope': 'GIGACHAT_API_PERS'}
            
            response = requests.post(
                'https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
                headers=headers,
                data=data,
                verify=False,  # Для самоподписанного сертификата
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                self.auth_token = result['access_token']
                self.token_expires = time.time() + result['expires_in'] - 60
                logger.info("✅ Токен GigaChat получен")
                return self.auth_token
            else:
                logger.error(f"❌ Ошибка получения токена: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка при получении токена: {e}")
            return None
    
    def generate_with_image(self, prompt: str, image_bytes: bytes, model: str = 'GigaChat-2-Max') -> Optional[Tuple[str, str]]:
        """
        Генерирует название и описание по фото
        Возвращает кортеж (название, описание)
        """
        token = self._get_auth_token()
        if not token:
            return None
        
        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            # Если есть изображение, кодируем его в base64
            content = prompt
            if image_bytes:
                image_base64 = base64.b64encode(image_bytes).decode()
                content = f"{prompt}\n\n[IMG]{image_base64}[/IMG]"
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                'https://gigachat.devices.sberbank.ru/api/v1/chat/completions',
                headers=headers,
                json=payload,
                verify=False,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result['choices'][0]['message']['content']
                
                # Парсим ответ
                lines = text.split('\n')
                name = "Волшебный букет"
                description = "Нежный букет для особенного случая."
                
                for line in lines:
                    if line.startswith('Название:'):
                        name = line.replace('Название:', '').strip()
                    elif line.startswith('Описание:'):
                        description = line.replace('Описание:', '').strip()
                
                logger.info(f"✅ GigaChat сгенерировал: {name}")
                return name, description
            else:
                logger.error(f"❌ Ошибка GigaChat: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка при запросе к GigaChat: {e}")
            return None
