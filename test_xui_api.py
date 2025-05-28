import os
import requests
from dotenv import load_dotenv

load_dotenv()

XUI_HOST = os.getenv('XUI_HOST')
XUI_PORT = os.getenv('XUI_PORT')
XUI_USERNAME = os.getenv('XUI_USERNAME')
XUI_PASSWORD = os.getenv('XUI_PASSWORD')
XUI_PREFIX = os.getenv('XUI_PREFIX', '').strip('/')

if XUI_PREFIX:
    base_url = f"http://{XUI_HOST}:{XUI_PORT}/{XUI_PREFIX}"
else:
    base_url = f"http://{XUI_HOST}:{XUI_PORT}"

login_url = f"{base_url}/login"
inbounds_url = f"{base_url}/panel/api/inbounds/list"

session = requests.Session()

print(f"[TEST] Попытка авторизации по URL: {login_url}")
resp = session.get(login_url)
print(f"[TEST] GET /login: {resp.status_code}")
print(f"[TEST] Headers: {resp.headers}")

resp = session.post(
    login_url,
    json={"username": XUI_USERNAME, "password": XUI_PASSWORD},
    headers={
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': base_url,
        'Referer': login_url
    }
)
print(f"[TEST] POST /login: {resp.status_code}")
print(f"[TEST] Тело ответа: {resp.text}")
print(f"[TEST] Cookies после авторизации: {session.cookies}")

print(f"[TEST] Запрос списка inbounds: {inbounds_url}")
resp = session.get(
    inbounds_url,
    headers={
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': base_url,
        'Referer': f"{base_url}/panel/inbounds"
    }
)
print(f"[TEST] GET /panel/api/inbounds/list: {resp.status_code}")
print(f"[TEST] Тело ответа: {resp.text[:1000]}{'...' if len(resp.text) > 1000 else ''}") 