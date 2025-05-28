import os
import sys
import subprocess
import time
import signal
from dotenv import load_dotenv
import logging
import traceback

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('logs/run.log', encoding='utf-8'),
        logging.StreamHandler()  # Также выводим в консоль
    ]
)
logger = logging.getLogger(__name__)

def check_requirements():
    """Проверка и установка необходимых пакетов"""
    required_packages = [
        'python-telegram-bot',
        'sqlalchemy',
        'python-dotenv',
        'requests'
    ]
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            logger.info(f"Установка {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def check_env():
    """Проверка наличия всех необходимых переменных окружения"""
    required_vars = [
        'TELEGRAM_TOKEN',
        'ADMIN_BOT_TOKEN',
        'ADMIN_ID',
        'XUI_HOST',
        'XUI_PORT',
        'XUI_USERNAME',
        'XUI_PASSWORD'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error("❌ Отсутствуют следующие переменные окружения:")
        for var in missing_vars:
            logger.error(f"  - {var}")
        return False
    return True

def run_bot(script_name, max_retries=3, retry_delay=5):
    """Запуск бота в отдельном процессе с автоматическим перезапуском"""
    retries = 0
    while retries < max_retries:
        try:
            process = subprocess.Popen(
                [sys.executable, script_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1  # Линейная буферизация
            )
            logger.info(f"✅ {script_name} успешно запущен")
            return process
        except Exception as e:
            retries += 1
            logger.error(f"❌ Ошибка при запуске {script_name} (попытка {retries}/{max_retries}): {e}")
            if retries < max_retries:
                logger.info(f"⏳ Ожидание {retry_delay} секунд перед повторной попыткой...")
                time.sleep(retry_delay)
            else:
                logger.error(f"❌ Не удалось запустить {script_name} после {max_retries} попыток")
                return None

def restart_bot(process, script_name):
    """Перезапуск бота при сбое"""
    if process:
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            process.kill()
    
    logger.info(f"🔄 Перезапуск {script_name}...")
    return run_bot(script_name)

def main():
    # Создаем директорию для логов, если её нет
    os.makedirs('logs', exist_ok=True)
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Проверяем зависимости
    logger.info("🔍 Проверка зависимостей...")
    check_requirements()
    
    # Проверяем переменные окружения
    logger.info("🔍 Проверка переменных окружения...")
    if not check_env():
        logger.error("❌ Пожалуйста, заполните все необходимые переменные в файле .env")
        return
    
    # Запускаем боты
    logger.info("🚀 Запуск ботов...")
    
    # Запускаем основной бот
    main_bot = run_bot("bot.py")
    if not main_bot:
        logger.error("❌ Не удалось запустить основной бот")
        return
    
    # Ждем 5 секунд перед запуском админ-бота
    time.sleep(5)
    
    # Запускаем админ-бот
    admin_bot = run_bot("admin_bot.py")
    if not admin_bot:
        logger.error("❌ Не удалось запустить админ-бот")
        main_bot.terminate()
        return
    
    def signal_handler(signum, frame):
        logger.info("\n🛑 Остановка ботов...")
        if main_bot:
            main_bot.terminate()
        if admin_bot:
            admin_bot.terminate()
        logger.info("✅ Боты остановлены")
        sys.exit(0)
    
    # Регистрируем обработчик сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Мониторим вывод ботов
        while True:
            if main_bot:
                try:
                    output = main_bot.stdout.readline()
                    if output:
                        logger.info(f"[Основной бот] {output.strip()}")
                    
                    # Проверяем наличие ошибок
                    error = main_bot.stderr.readline()
                    if error:
                        logger.error(f"[Основной бот] Ошибка: {error.strip()}")
                except Exception as e:
                    logger.error(f"Ошибка при чтении вывода основного бота: {e}")
                    main_bot = restart_bot(main_bot, "bot.py")
            
            if admin_bot:
                try:
                    output = admin_bot.stdout.readline()
                    if output:
                        logger.info(f"[Админ-бот] {output.strip()}")
                    
                    # Проверяем наличие ошибок
                    error = admin_bot.stderr.readline()
                    if error:
                        logger.error(f"[Админ-бот] Ошибка: {error.strip()}")
                except Exception as e:
                    logger.error(f"Ошибка при чтении вывода админ-бота: {e}")
                    admin_bot = restart_bot(admin_bot, "admin_bot.py")
            
            # Проверяем, не завершились ли боты
            if main_bot and main_bot.poll() is not None:
                logger.error("❌ Основной бот завершил работу")
                main_bot = restart_bot(main_bot, "bot.py")
            
            if admin_bot and admin_bot.poll() is not None:
                logger.error("❌ Админ-бот завершил работу")
                admin_bot = restart_bot(admin_bot, "admin_bot.py")
            
            time.sleep(0.1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}\n{traceback.format_exc()}")
        signal_handler(signal.SIGTERM, None)

if __name__ == "__main__":
    logger.info("Запуск бота...")
    main() 