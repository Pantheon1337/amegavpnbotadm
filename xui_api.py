import requests
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import os

# Создаем директорию для логов, если её нет
os.makedirs('logs', exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/xui_api.log', encoding='utf-8'),
        logging.StreamHandler()  # Также выводим в консоль
    ]
)
logger = logging.getLogger('XUIApi')

class XUIApi:
    def __init__(self, host: str, port: int, username: str = None, password: str = None, token: str = None, prefix: str = None):
        self.prefix = prefix or os.getenv('XUI_PREFIX', '').strip('/')
        if self.prefix:
            self.base_url = f"https://{host}:{port}/{self.prefix}/panel"
        else:
            self.base_url = f"https://{host}:{port}/panel"
        self.token = token or os.getenv('XUI_TOKEN')
        self.session = requests.Session()
        logger.info(f"Инициализация XUIApi с URL: {self.base_url} (токен: {self.token[:10]}...)")

    def get_client_status(self, email: str, xui_id: str = None) -> Dict[str, Any]:
        print(f"[DEBUG] Вызван get_client_status: email={email}, xui_id={xui_id}")
        try:
            list_url = f"{self.base_url}/api/inbounds/list"
            logger.debug(f"[get_client_status] URL: {list_url}, email: {email}, xui_id: {xui_id}")
            
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Content-Type': 'application/json',
                'X-UI-Token': self.token,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Origin': self.base_url,
                'Referer': f"{self.base_url}/",
                'Connection': 'keep-alive'
            }
            logger.debug(f"[get_client_status] Headers: {headers}")
            
            response = self.session.get(
                list_url,
                headers=headers,
                verify=False,  # Отключаем проверку SSL для тестирования
                allow_redirects=True  # Разрешаем редиректы
            )
            logger.debug(f"[get_client_status] Response status: {response.status_code}")
            logger.debug(f"[get_client_status] Response text: {response.text[:500]}...")  # Логируем только первые 500 символов
            
            if response.status_code == 307:
                logger.error("[get_client_status] Получен редирект - возможно, неверный токен или URL")
                return None
                
            response.raise_for_status()
            
            if not response.text:
                logger.error("[get_client_status] Получен пустой ответ от сервера")
                return None
                
            try:
                inbounds = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"[get_client_status] Ошибка при разборе JSON: {str(e)}")
                logger.error(f"[get_client_status] Содержимое ответа: {response.text[:500]}...")
                return None
                
            logger.debug(f"[get_client_status] Полученные данные inbounds: {json.dumps(inbounds, indent=2)}")
            
            if not isinstance(inbounds, dict):
                logger.error(f"[get_client_status] Неверный формат ответа: {inbounds}")
                return None
                
            if not inbounds.get('success'):
                logger.error(f"[get_client_status] Ошибка получения списка inbounds: {inbounds.get('msg', 'Неизвестная ошибка')}")
                return None
                
            # Ищем клиента по email или id в поле clientStats
            for inbound in inbounds.get('obj', []):
                client_stats = inbound.get('clientStats', [])
                for client in client_stats:
                    found = False
                    if client.get('email') == email:
                        found = True
                    if xui_id and client.get('id') == xui_id:
                        found = True
                    if found:
                        real_email = client.get('email')
                        logger.info(f"[get_client_status] Найден клиент с email {real_email} или id {xui_id}")
                        # Используем данные из clientStats
                        used_bytes = client.get('up', 0) + client.get('down', 0)
                        total_gb = float(client.get('total', 0)) / (1024 * 1024 * 1024)  # Конвертируем байты в ГБ
                        used_gb = used_bytes / (1024 * 1024 * 1024)
                        remaining_gb = max(0, total_gb - used_gb)
                        result = {
                            'status': 'active' if client.get('enable', True) else 'disabled',
                            'expiry': client.get('expiryTime', 0),
                            'total': client.get('total', 0),
                            'used': used_bytes,
                            'remaining': remaining_gb * (1024 * 1024 * 1024)
                        }
                        logger.debug(f"[get_client_status] Результат для клиента: {json.dumps(result, indent=2)}")
                        return result
                        
            logger.warning(f"[get_client_status] Клиент с email {email} или id {xui_id} не найден")
            return None
            
        except Exception as e:
            import traceback
            logger.error(f"[get_client_status] Ошибка при получении статуса клиента: {str(e)}\n{traceback.format_exc()}")
            return None

    def get_client_stats(self, inbound_id: int, email: str) -> Optional[Dict[str, int]]:
        """Получение статистики использования клиента"""
        try:
            stats_url = f"{self.base_url}/api/inbounds/getClientStats/{inbound_id}"
            logger.debug(f"[get_client_stats] URL: {stats_url}, inbound_id: {inbound_id}, email: {email}")
            response = self.session.get(
                stats_url,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-UI-Token': self.token,
                }
            )
            logger.debug(f"[get_client_stats] Response status: {response.status_code}")
            logger.debug(f"[get_client_stats] Response text: {response.text}")
            response.raise_for_status()
            if not response.text:
                logger.error("[get_client_stats] Получен пустой ответ от сервера")
                return None
            try:
                stats = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"[get_client_stats] Ошибка при разборе JSON: {str(e)}")
                logger.error(f"[get_client_stats] Содержимое ответа: {response.text}")
                return None
            logger.debug(f"[get_client_stats] Полученные данные статистики: {json.dumps(stats, indent=2)}")
            if not stats.get('success'):
                logger.error(f"[get_client_stats] Ошибка получения статистики: {stats}")
                return None
            client_stats = stats.get('obj', {}).get(email, {})
            result = {
                'up': client_stats.get('up', 0),
                'down': client_stats.get('down', 0)
            }
            logger.debug(f"[get_client_stats] Статистика для клиента: {json.dumps(result, indent=2)}")
            return result
        except Exception as e:
            import traceback
            logger.error(f"[get_client_stats] Ошибка при получении статистики клиента: {str(e)}\n{traceback.format_exc()}")
            return None 