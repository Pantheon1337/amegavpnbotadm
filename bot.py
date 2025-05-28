import os
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
from datetime import datetime, timedelta, time
from xui_api import XUIApi
import httpx
import traceback
import sys

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('logs/log.txt', encoding='utf-8'),
        logging.StreamHandler()  # Также выводим в консоль
    ]
)

# Настройка логирования для httpx
httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.WARNING)  # Устанавливаем уровень WARNING для httpx

logger = logging.getLogger(__name__)

# Создаем директорию для логов, если её нет
os.makedirs('logs', exist_ok=True)

# Добавляем файловый обработчик для логов
file_handler = logging.FileHandler('logs/bot.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Состояния для ConversationHandler
PAYMENT_INFO, WAITING_PAYMENT, CHECKING_PAYMENT = range(3)

# Создание базы данных
Base = declarative_base()
engine = create_engine('sqlite:///vpn_keys.db')
Session = sessionmaker(bind=engine)

class VPNKey(Base):
    __tablename__ = 'vpn_keys'
    
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)
    is_used = Column(Boolean, default=False)
    user_id = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)  # Старое поле, можно оставить для обратной совместимости
    xui_email = Column(String, nullable=True)  # Новый идентификатор для x-ui
    xui_id = Column(String, nullable=True)  # Новый ID клиента из x-ui
    activation_date = Column(DateTime, default=datetime.utcnow)
    expiration_date = Column(DateTime)

class Payment(Base):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    username = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    status = Column(String)  # pending, approved, rejected
    receipt_path = Column(String, nullable=True)
    payment_date = Column(DateTime, default=datetime.utcnow)
    next_payment_date = Column(DateTime)

# Создаем таблицы, если они не существуют
def init_db():
    Base.metadata.create_all(engine)

# Инициализируем базу данных при запуске
init_db()

# Создание клавиатуры
def get_keyboard():
    keyboard = [
        ['🔐 Купить VPN', '📊 Статус VPN'],
        ['👨‍💻 Тех поддержка', '🤖 AmegaAI'],
        ['ℹ️ О нас']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Отправляем приветственное изображение
    try:
        with open('img/1.jpg', 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="🌟 *Добро пожаловать в AmegaVPN\!*\n\n"
                       "🔐 *Безопасный и быстрый VPN сервис*\n\n"
                       "Выберите действие в меню ниже:",
                parse_mode='MarkdownV2',
                reply_markup=get_keyboard()
            )
    except FileNotFoundError:
        await update.message.reply_text(
            "🌟 *Добро пожаловать в AmegaVPN\!*\n\n"
            "🔐 *Безопасный и быстрый VPN сервис*\n\n"
            "Выберите действие в меню ниже:",
            parse_mode='MarkdownV2',
            reply_markup=get_keyboard()
        )
    return ConversationHandler.END

async def buy_vpn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        # Проверяем наличие активного ключа
        existing_key = session.query(VPNKey).filter_by(
            user_id=update.effective_user.id,
            is_used=True
        ).first()
        
        if existing_key:
            # Проверяем, не истек ли срок действия
            if existing_key.activation_date:
                expiry_date = existing_key.activation_date + timedelta(days=30)
                if datetime.now() > expiry_date:
                    # Если срок истек, предлагаем купить новый ключ
                    payment_text = (
                        "💳 *Оплата VPN*\n\n"
                        "💰 *Стоимость:* 200₽ в месяц\n\n"
                        "📝 *После оплаты вы получите инструкцию с ключом доступа*\n\n"
                        "⚠️ *ВНИМАНИЕ\!*\n"
                        "Ключ рассчитан на *1 пользователя*\. При активации на других устройствах он будет заблокирован\.\n\n"
                        "*Способы оплаты:*\n"
                        "💳 *Тинькофф:* `2200 7009 0119 7003` \(ПРИОРИТЕТНЫЙ СПОСОБ ОПЛАТЫ\) Илья\.Г\n"
                        "💳 *Сбер:* `4276 4001 1192 0428` Илья\.Г\n"
                        "💰 *Bitcoin:* `1PXFB8LRTBqLLuxLWHA3Fcr3sht99BegwZ`\n"
                        "💰 *USDT \(TRC20\):* `TQJRXxoAG5ikM1t1Qrpfv2RKbtyhnkfJnb`\n"
                        "💰 *TON:* `UQA4V86WRe3ntN0Bf25mnT4P_CS6JOynw4V8GldE7ofoeCHq`\n\n"
                        "📸 После оплаты, пожалуйста, пришлите скриншот чека для подтверждения\."
                    )
                    
                    await update.message.reply_text(
                        payment_text,
                        parse_mode='MarkdownV2',
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📞 Техподдержка", url="https://t.me/ilyshapretty")
                        ]])
                    )
                    return WAITING_PAYMENT
                else:
                    # Если срок не истек, предлагаем продлить
                    days_left = (expiry_date - datetime.now()).days
                    await update.message.reply_text(
                        f"⚠️ *У вас уже есть активный ключ VPN\!*\n\n"
                        f"🔑 *Ваш текущий ключ:* `{existing_key.key}`\n"
                        f"⏳ *Осталось дней:* {days_left}\n\n"
                        "Для продления подписки используйте кнопку '🔄 Продлить подписку' в статусе VPN\.",
                        parse_mode='MarkdownV2',
                        reply_markup=get_keyboard()
                    )
                    return ConversationHandler.END
            else:
                # Если нет даты активации, предлагаем купить новый ключ
                payment_text = (
                    "💳 *Оплата VPN*\n\n"
                    "💰 *Стоимость:* 200₽ в месяц\n\n"
                    "📝 *После оплаты вы получите инструкцию с ключом доступа*\n\n"
                    "⚠️ *ВНИМАНИЕ\!*\n"
                    "Ключ рассчитан на *1 пользователя*\. При активации на других устройствах он будет заблокирован\.\n\n"
                    "*Способы оплаты:*\n"
                    "💳 *Тинькофф:* `2200 7009 0119 7003` \(ПРИОРИТЕТНЫЙ СПОСОБ ОПЛАТЫ\) Илья\.Г\n"
                    "💳 *Сбер:* `4276 4001 1192 0428` Илья\.Г\n"
                    "💰 *Bitcoin:* `1PXFB8LRTBqLLuxLWHA3Fcr3sht99BegwZ`\n"
                    "💰 *USDT \(TRC20\):* `TQJRXxoAG5ikM1t1Qrpfv2RKbtyhnkfJnb`\n"
                    "💰 *TON:* `UQA4V86WRe3ntN0Bf25mnT4P_CS6JOynw4V8GldE7ofoeCHq`\n\n"
                    "📸 После оплаты, пожалуйста, пришлите скриншот чека для подтверждения\."
                )
                
                await update.message.reply_text(
                    payment_text,
                    parse_mode='MarkdownV2',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📞 Техподдержка", url="https://t.me/ilyshapretty")
                    ]])
                )
                return WAITING_PAYMENT

        # Если нет активного ключа, предлагаем купить новый
        payment_text = (
            "💳 *Оплата VPN*\n\n"
            "💰 *Стоимость:* 200₽ в месяц\n\n"
            "📝 *После оплаты вы получите инструкцию с ключом доступа*\n\n"
            "⚠️ *ВНИМАНИЕ\!*\n"
            "Ключ рассчитан на *1 пользователя*\. При активации на других устройствах он будет заблокирован\.\n\n"
            "*Способы оплаты:*\n"
            "💳 *Тинькофф:* `2200 7009 0119 7003` \(ПРИОРИТЕТНЫЙ СПОСОБ ОПЛАТЫ\) Илья\.Г\n"
            "💳 *Сбер:* `4276 4001 1192 0428` Илья\.Г\n"
            "💰 *Bitcoin:* `1PXFB8LRTBqLLuxLWHA3Fcr3sht99BegwZ`\n"
            "💰 *USDT \(TRC20\):* `TQJRXxoAG5ikM1t1Qrpfv2RKbtyhnkfJnb`\n"
            "💰 *TON:* `UQA4V86WRe3ntN0Bf25mnT4P_CS6JOynw4V8GldE7ofoeCHq`\n\n"
            "📸 После оплаты, пожалуйста, пришлите скриншот чека для подтверждения\."
        )
        
        await update.message.reply_text(
            payment_text,
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📞 Техподдержка", url="https://t.me/ilyshapretty")
            ]])
        )
        return WAITING_PAYMENT
    finally:
        session.close()

async def handle_payment_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text(
            "❌ *Ошибка\!*\n"
            "Пожалуйста, отправьте скриншот чека об оплате\.",
            parse_mode='MarkdownV2'
        )
        return WAITING_PAYMENT

    try:
        # Создаем директорию для чеков, если она не существует
        os.makedirs('receipts', exist_ok=True)

        # Сохраняем фото
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        receipt_path = f"receipts/{update.effective_user.id}_{update.message.message_id}.jpg"
        await file.download_to_drive(receipt_path)

        # Получаем информацию о пользователе
        user = update.effective_user
        username = f"@{user.username}" if user.username else None
        phone = user.phone_number if hasattr(user, 'phone_number') else None

        # Сохраняем информацию о платеже
        session = Session()
        payment = Payment(
            user_id=update.effective_user.id,
            username=username,
            phone=phone,
            status='pending',
            receipt_path=receipt_path,
            payment_date=datetime.utcnow(),
            next_payment_date=datetime.utcnow() + timedelta(days=30)
        )
        session.add(payment)
        session.commit()
        payment_id = payment.id
        session.close()

        # Отправляем уведомление администратору
        admin_id = int(os.getenv('ADMIN_ID'))
        try:
            admin_bot = Application.builder().token(os.getenv('ADMIN_BOT_TOKEN')).build()
            keyboard = [
                [
                    InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{payment_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{payment_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            with open(receipt_path, 'rb') as photo_file:
                await admin_bot.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo_file,
                    caption=f"📨 *Новый платеж*\n\n"
                           f"👤 *Пользователь:*\n"
                           f"ID: `{user.id}`\n"
                           f"Username: {username or 'Не указан'}\n"
                           f"Телефон: `{phone or 'Не указан'}`\n\n"
                           f"🆔 *ID платежа:* `{payment_id}`\n"
                           f"📊 *Статус:* Ожидает подтверждения",
                    parse_mode='MarkdownV2',
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления администратору: {e}")
            await update.message.reply_text(
                "❌ *Произошла ошибка при отправке чека администратору\.*\n"
                "Пожалуйста, попробуйте позже или обратитесь в техподдержку\.",
                parse_mode='MarkdownV2'
            )
            return WAITING_PAYMENT

        await update.message.reply_text(
            "✅ *Спасибо\!*\n\n"
            "📝 Ваш чек отправлен на проверку\.\n"
            "🔑 Вы получите ключ VPN сразу после подтверждения оплаты\.",
            parse_mode='MarkdownV2'
        )
        return CHECKING_PAYMENT
    except Exception as e:
        logger.error(f"Ошибка при обработке чека: {e}")
        await update.message.reply_text(
            "❌ *Произошла ошибка при обработке чека\.*\n"
            "Пожалуйста, попробуйте позже или обратитесь в техподдержку\.",
            parse_mode='MarkdownV2'
        )
        return WAITING_PAYMENT

async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, не является ли сообщение командой меню
    if update.message.text in ['🔐 Купить VPN', '📊 Статус VPN', '👨‍💻 Тех поддержка', '🤖 AmegaAI', 'ℹ️ О нас']:
        return await handle_message(update, context)

    session = Session()
    try:
        payment = session.query(Payment).filter_by(
            user_id=update.effective_user.id,
            status='pending'
        ).first()

        if payment and payment.status == 'approved':
            # Выдаем ключ
            available_key = session.query(VPNKey).filter_by(is_used=False).first()
            if available_key:
                available_key.is_used = True
                available_key.user_id = update.effective_user.id
                available_key.activation_date = datetime.now()
                key = available_key.key
                identifier = key.split('#')[-1] if '#' in key else None
                if identifier and identifier.startswith('AmegaVPN-'):
                    identifier = identifier[len('AmegaVPN-'):]
                available_key.xui_email = identifier
                xui_id = None
                try:
                    xui_id = key.split('://')[1].split('@')[0]
                except Exception:
                    pass
                available_key.xui_id = xui_id
                session.commit()
                
                keyboard = [
                    [InlineKeyboardButton("📋 Скопировать ключ", callback_data=f"copy_{available_key.id}")],
                    [InlineKeyboardButton("📊 Статус VPN", callback_data="vpn_status")]
                ]
                
                await update.message.reply_text(
                    "🎉 *Оплата подтверждена\!*\n\n"
                    f"🔑 *Ваш ключ VPN:*\n"
                    f"`{available_key.key}`\n\n"
                    "📱 *Используйте его для подключения к VPN сервису*\n\n"
                    "⚠️ *Важно:* Не передавайте ключ третьим лицам\!",
                    parse_mode='MarkdownV2',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                await vpn_status(update, context)
                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    "❌ *Ошибка\!*\n\n"
                    "К сожалению, в данный момент нет доступных ключей\.\n"
                    "Пожалуйста, обратитесь в техподдержку\.",
                    parse_mode='MarkdownV2',
                    reply_markup=get_keyboard()
                )
                return ConversationHandler.END
        elif payment and payment.status == 'rejected':
            # Обновляем статус платежа
            payment.status = 'rejected'
            session.commit()
            
            # Сбрасываем состояние бота
            context.user_data.clear()
            
            await update.message.reply_text(
                "❌ *Платеж отклонен\!*\n\n"
                "Пожалуйста, проверьте правильность оплаты и попробуйте снова или обратитесь в техподдержку\.",
                parse_mode='MarkdownV2',
                reply_markup=get_keyboard()
            )
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "⏳ *Платеж проверяется*\n\n"
                "Вы получите ключ сразу после подтверждения оплаты\.",
                parse_mode='MarkdownV2',
                reply_markup=get_keyboard()
            )
            return CHECKING_PAYMENT
    finally:
        session.close()

def get_location_from_key(key: str) -> str:
    """Определяет локацию из ключа VPN"""
    try:
        # Ищем часть ключа после #AmegaVPN-vpn-
        if '#AmegaVPN-vpn-' in key:
            location_part = key.split('#AmegaVPN-vpn-')[1].split('-')[0].lower()
            
            # Словарь соответствия локаций
            locations = {
                'germany': 'Германия',
                'bulgary': 'Болгария',
                'austria': 'Австрия',
                'france': 'Франция'
            }
            
            return locations.get(location_part, 'Неизвестная локация')
    except Exception as e:
        logger.error(f"Ошибка при определении локации из ключа: {e}")
    return 'Неизвестная локация'

async def vpn_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка статуса VPN"""
    try:
        # Определяем, откуда пришел запрос
        if update.callback_query:
            user_id = update.callback_query.from_user.id
            message = update.callback_query.message
            logger.info(f"Получен callback-запрос для статуса VPN от пользователя {user_id}")
        else:
            user_id = update.effective_user.id
            message = update.message
            logger.info(f"Получен запрос статуса VPN от пользователя {user_id}")

        # Получаем ключ пользователя из базы данных
        with Session() as session:
            logger.debug(f"Поиск ключа VPN для пользователя {user_id} в базе данных")
            user = session.query(VPNKey).filter(VPNKey.user_id == user_id).first()
            
            if not user:
                logger.warning(f"Ключ VPN не найден для пользователя {user_id}")
                text = (
                    "❌ У вас нет активного ключа VPN.\n\n"
                    "Для покупки ключа нажмите кнопку '🔐 Купить VPN'."
                )
                if update.callback_query:
                    await update.callback_query.message.reply_text(text)
                else:
                    await update.message.reply_text(text)
                return

            logger.info(f"Найден ключ VPN для пользователя {user_id}: {user.key}")
            
            # Получаем дату покупки ключа
            purchase_date = user.activation_date
            if not purchase_date:
                logger.warning(f"Дата активации не указана для пользователя {user_id}, используем текущую дату")
                purchase_date = datetime.now()
                
            # Вычисляем дату окончания (30 дней с момента покупки)
            expiry_date = purchase_date + timedelta(days=30)
            logger.debug(f"Дата окончания для пользователя {user_id}: {expiry_date}")
            
            # Проверяем, не истек ли срок действия
            if datetime.now() > expiry_date:
                status_text = "❌ Истек срок действия"
                logger.info(f"Срок действия истек для пользователя {user_id}")
            else:
                status_text = "✅ Активен"
                logger.info(f"Ключ активен для пользователя {user_id}")
                
            # Форматируем даты
            purchase_date_str = purchase_date.strftime("%d.%m.%Y")
            expiry_date_str = expiry_date.strftime("%d.%m.%Y")
            
            # Получаем локацию из ключа
            location = get_location_from_key(user.key)
            logger.debug(f"Определена локация для пользователя {user_id}: {location}")
            
            # Формируем сообщение
            message_text = (
                f"📊 *Статус вашего VPN*\n\n"
                f"🔑 *Ключ:* `{user.key}`\n"
                f"📡 *Локация:* {location}\n"
                f"📅 *Дата покупки:* {purchase_date_str}\n"
                f"⏳ *Срок действия:* {expiry_date_str}\n"
                f"📊 *Статус:* {status_text}\n\n"
            )
            
            # Добавляем кнопки
            keyboard = [
                [InlineKeyboardButton("📋 Скопировать ключ", callback_data=f"copy_{user.id}")],
            ]
            if status_text == "✅ Активен":
                keyboard.append([InlineKeyboardButton("🔄 Продлить подписку", callback_data="renew_vpn")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            logger.debug(f"Отправка сообщения со статусом VPN пользователю {user_id}")
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            logger.info(f"Сообщение со статусом VPN успешно отправлено пользователю {user_id}")
            
    except Exception as e:
        logger.error(f"Ошибка при получении статуса VPN: {str(e)}\n{traceback.format_exc()}")
        error_text = (
            "❌ Произошла ошибка при получении статуса VPN.\n"
            "Пожалуйста, попробуйте позже или обратитесь в техподдержку."
        )
        try:
            if update.callback_query:
                await update.callback_query.message.reply_text(error_text)
            else:
                await update.message.reply_text(error_text)
        except Exception as send_error:
            logger.error(f"Ошибка при отправке сообщения об ошибке: {str(send_error)}")

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("👨‍💻 Администратор", url="https://t.me/ilyshapretty"),
            InlineKeyboardButton("📢 Наш канал", url="https://t.me/vpn_amega")
        ]
    ]
    
    await update.message.reply_text(
        "👨‍💻 *Техническая поддержка*\n\n"
        "Для получения помощи, пожалуйста, напишите:\n"
        "👨‍💻 Администратору: @ilyshapretty\n\n"
        "📢 *Наш канал:* @vpn\_amega\n\n"
        "Наш специалист свяжется с вами в ближайшее время\.",
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Добавляем обработчик для копирования ключа
async def copy_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    key_id = int(query.data[5:])
    session = Session()
    key = session.query(VPNKey).filter(VPNKey.id == key_id).first()
    if key:
        await query.answer(f"Ключ скопирован: {key.key}", show_alert=True)
        await query.message.reply_text(
            f"🔑 *Ваш ключ VPN:*\n`{key.key}`\n\n"
            "📱 *Используйте его для подключения к VPN сервису*\n\n"
            "⚠️ *Важно:* Не передавайте ключ третьим лицам\!",
            parse_mode='MarkdownV2'
        )
    else:
        logger.error(f"Ключ с ID {key_id} не найден в базе данных")
        await query.message.reply_text(
            "❌ *Ошибка при копировании ключа*\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в техподдержку\.",
            parse_mode='MarkdownV2'
        )
    session.close()

async def amegaai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход к AmegaAI боту"""
    keyboard = [[
        InlineKeyboardButton("🤖 Перейти к AmegaAI", url="https://t.me/amegaai_bot")
    ]]
    
    await update.message.reply_text(
        "🤖 *AmegaAI \- ИИ чат бот*\n\n"
        "Умный ИИ ассистент для общения и помощи\.\n"
        "Нажмите кнопку ниже, чтобы начать общение с ботом\.",
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def about_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о VPN сервисе"""
    keyboard = [
        [
            InlineKeyboardButton("🌐 Сайт разработчика", url="https://ilyshagavrilov.ru"),
            InlineKeyboardButton("👨‍💻 Администратор", url="https://t.me/ilyshapretty")
        ],
        [
            InlineKeyboardButton("📢 Наш канал", url="https://t.me/vpn_amega")
        ]
    ]
    
    await update.message.reply_text(
        "🌟 *О AmegaVPN*\n\n"
        "🔐 *Безопасность:*\n"
        "• Шифрование военного уровня\n"
        "• Защита от утечек DNS\n"
        "• Отсутствие логирования\n\n"
        "⚡️ *Скорость:*\n"
        "• Высокоскоростные серверы\n"
        "• Оптимизированная сеть\n"
        "• Стабильное соединение\n\n"
        "🌍 *Локации:*\n"
        "• Серверы в Германии,Австрии,Болгарии,Франции\n"
        "• Низкий пинг\n"
        "• Высокая стабильность\n\n"
        "💎 *Преимущества:*\n"
        "• Простая настройка\n"
        "• Поддержка 24/7\n"
        "• Доступная цена\n\n"
        "🔗 *Полезные ссылки:*",
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == '🔐 Купить VPN':
        return await buy_vpn(update, context)
    elif text == '📊 Статус VPN':
        return await vpn_status(update, context)
    elif text == '👨‍💻 Тех поддержка':
        return await support(update, context)
    elif text == '🤖 AmegaAI':
        return await amegaai(update, context)
    elif text == 'ℹ️ О нас':
        return await about_us(update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки меню для навигации.",
            reply_markup=get_keyboard()
        )
        return ConversationHandler.END

# Добавляем функцию для отправки уведомлений об оплате
async def send_payment_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Отправка напоминаний об оплате"""
    session = Session()
    now = datetime.utcnow()
    
    # Получаем все активные ключи
    active_keys = session.query(VPNKey).filter_by(is_used=True).all()
    
    for key in active_keys:
        if key.activation_date:
            # Вычисляем дату окончания (30 дней с момента активации)
            expiry_date = key.activation_date + timedelta(days=30)
            days_until_expiration = (expiry_date - now).days
            
            # Отправляем напоминания за 5, 3 и 1 день
            if days_until_expiration in [5, 3, 1]:
                try:
                    message = (
                        f"⚠️ *Напоминание об оплате\!*\n\n"
                        f"До окончания подписки осталось *{days_until_expiration}* "
                        f"{'день' if days_until_expiration == 1 else 'дня' if days_until_expiration in [2,3,4] else 'дней'}\.\n\n"
                        f"Для продления подписки используйте кнопку '🔐 Купить VPN'\."
                    )
                    
                    await context.bot.send_message(
                        chat_id=key.user_id,
                        text=message,
                        parse_mode='MarkdownV2',
                        reply_markup=get_keyboard()
                    )
                    logger.info(f"Отправлено напоминание пользователю {key.user_id} за {days_until_expiration} дней")
                except Exception as e:
                    logger.error(f"Ошибка при отправке напоминания пользователю {key.user_id}: {e}")
    
    session.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка справки по командам"""
    help_text = (
        "🤖 *AmegaVPN Bot*\n\n"
        "*Доступные команды:*\n"
        "/start \- Начать работу с ботом\n"
        "/help \- Показать это сообщение\n\n"
        "*Основные функции:*\n"
        "• 🔐 Купить VPN \- Приобрести подписку\n"
        "• 📊 Статус VPN \- Проверить статус подписки\n"
        "• 👨‍💻 Тех поддержка \- Связаться с поддержкой"
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode='MarkdownV2',
        reply_markup=get_keyboard()
    )
    return ConversationHandler.END

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"Получен callback: {query.data}")
    try:
        if query.data.startswith("copy_"):
            # Получаем ID ключа из callback_data
            key_id = int(query.data[5:])
            # Получаем ключ из базы данных
            session = Session()
            key = session.query(VPNKey).filter(VPNKey.id == key_id).first()
            if key:
                await query.message.reply_text(
                    f"🔑 *Ваш ключ VPN:*\n`{key.key}`\n\n"
                    "📱 *Используйте его для подключения к VPN сервису*\n\n"
                    "⚠️ *Важно:* Не передавайте ключ третьим лицам\!",
                    parse_mode='MarkdownV2'
                )
            else:
                logger.error(f"Ключ с ID {key_id} не найден в базе данных")
                await query.message.reply_text(
                    "❌ *Ошибка при копировании ключа*\n\n"
                    "Пожалуйста, попробуйте позже или обратитесь в техподдержку\.",
                    parse_mode='MarkdownV2'
                )
        elif query.data == "renew_vpn":
            # Переход к продлению VPN
            payment_text = (
                "💳 *Продление VPN*\n\n"
                "💰 *Стоимость:* 200₽ в месяц\n\n"
                "📝 *После оплаты ваш ключ будет автоматически продлен*\n\n"
                "⚠️ *ВНИМАНИЕ\!*\n"
                "Ключ рассчитан на *1 пользователя*\. При активации на других устройствах он будет заблокирован\.\n\n"
                "*Способы оплаты:*\n"
                "💳 *Тинькофф:* `2200 7009 0119 7003` \(ПРИОРИТЕТНЫЙ СПОСОБ ОПЛАТЫ\) Илья\.Г\n"
                "💳 *Сбер:* `4276 4001 1192 0428` Илья\.Г\n"
                "💰 *Bitcoin:* `1PXFB8LRTBqLLuxLWHA3Fcr3sht99BegwZ`\n"
                "💰 *USDT \(TRC20\):* `TQJRXxoAG5ikM1t1Qrpfv2RKbtyhnkfJnb`\n"
                "💰 *TON:* `UQA4V86WRe3ntN0Bf25mnT4P_CS6JOynw4V8GldE7ofoeCHq`\n\n"
                "📸 После оплаты, пожалуйста, пришлите скриншот чека для подтверждения\."
            )
            
            await query.message.reply_text(
                payment_text,
                parse_mode='MarkdownV2',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📞 Техподдержка", url="https://t.me/ilyshapretty")
                ]])
            )
            return WAITING_PAYMENT
        elif query.data == "buy_vpn":
            # Переход к покупке VPN
            return await buy_vpn(update, context)
        elif query.data == "vpn_status":
            return await vpn_status(update, context)
        elif query.data == "support":
            return await support(update, context)
        elif query.data.startswith("approve_"):
            # Обработка подтверждения платежа
            payment_id = int(query.data.split("_")[1])
            await handle_payment_action(update, context, "approve", payment_id)
        elif query.data.startswith("reject_"):
            # Обработка отклонения платежа
            payment_id = int(query.data.split("_")[1])
            await handle_payment_action(update, context, "reject", payment_id)
        else:
            logger.warning(f"Неизвестный callback: {query.data}")
            await query.message.reply_text(
                "Пожалуйста, используйте кнопки меню для навигации.",
                reply_markup=get_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка в обработке callback: {str(e)}")
        await query.message.reply_text(
            "❌ *Произошла ошибка*\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в техподдержку\.",
            parse_mode='MarkdownV2'
        )

async def handle_payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, payment_id: int):
    session = Session()
    try:
        payment = session.query(Payment).filter_by(id=payment_id).first()
        if not payment:
            logger.error(f"Платеж с ID {payment_id} не найден")
            return
            
        payment.status = action
        session.commit()
        logger.info(f"Платеж {payment_id} {action}ed")
        
        # Отправляем уведомление пользователю
        try:
            if action == 'approved':
                message = "✅ *Ваш платеж подтвержден\!*\n\nВы получите ключ VPN в ближайшее время\."
            else:
                message = "❌ *Ваш платеж отклонен\!*\n\nПожалуйста, проверьте правильность оплаты и попробуйте снова или обратитесь в техподдержку\."
            
            # Создаем новую клавиатуру для пользователя
            keyboard = [
                ['🔐 Купить VPN', '📊 Статус VPN'],
                ['👨‍💻 Тех поддержка', '🤖 AmegaAI'],
                ['ℹ️ О нас']
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await context.bot.send_message(
                chat_id=payment.user_id,
                text=message,
                parse_mode='MarkdownV2',
                reply_markup=reply_markup
            )
            
            # Сбрасываем состояние бота для пользователя
            if action == 'rejected':
                context.user_data.clear()
                # Принудительно завершаем разговор
                return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления пользователю: {e}")
        
        await update.callback_query.message.reply_text(
            f"✅ *Платеж {action}ed\!*",
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке платежа: {str(e)}")
    finally:
        session.close()

def main():
    try:
        # Создание приложения с настройками для httpx и персистентности
        application = (
            Application.builder()
            .token(os.getenv('TELEGRAM_TOKEN'))
            .http_version('1.1')  # Используем HTTP/1.1 вместо HTTP/2
            .get_updates_http_version('1.1')
            .persistence(None)  # Отключаем персистентность на уровне приложения
            .build()
        )
        
        # Создание ConversationHandler для обработки процесса оплаты
        conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex('^🔐 Купить VPN$'), buy_vpn),
                CallbackQueryHandler(buy_vpn, pattern='^renew_vpn$')
            ],
            states={
                WAITING_PAYMENT: [
                    MessageHandler(filters.PHOTO, handle_payment_receipt),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
                ],
                CHECKING_PAYMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, check_payment_status)
                ]
            },
            fallbacks=[
                CommandHandler('start', start),
                CommandHandler('help', help_command),
                MessageHandler(filters.Regex('^🔐 Купить VPN$'), buy_vpn),
                MessageHandler(filters.Regex('^📊 Статус VPN$'), vpn_status),
                MessageHandler(filters.Regex('^👨‍💻 Тех поддержка$'), support),
                MessageHandler(filters.Regex('^🤖 AmegaAI$'), amegaai),
                MessageHandler(filters.Regex('^ℹ️ О нас$'), about_us)
            ],
            allow_reentry=True,
            persistent=False,  # Отключаем персистентность для ConversationHandler
            name='payment_conversation',
            per_message=False,  # Отключаем отслеживание для каждого сообщения
            per_chat=True,  # Включаем отслеживание для каждого чата
            per_user=True  # Включаем отслеживание для каждого пользователя
        )

        # Добавление обработчиков
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        
        # Добавляем обработчик callback-запросов перед другими обработчиками
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Добавляем отдельные обработчики для каждой кнопки меню
        application.add_handler(MessageHandler(filters.Regex('^🔐 Купить VPN$'), buy_vpn))
        application.add_handler(MessageHandler(filters.Regex('^📊 Статус VPN$'), vpn_status))
        application.add_handler(MessageHandler(filters.Regex('^👨‍💻 Тех поддержка$'), support))
        application.add_handler(MessageHandler(filters.Regex('^🤖 AmegaAI$'), amegaai))
        application.add_handler(MessageHandler(filters.Regex('^ℹ️ О нас$'), about_us))
        
        # Добавляем общий обработчик для остальных сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Добавляем job для отправки напоминаний об оплате
        job_queue = application.job_queue
        job_queue.run_daily(send_payment_reminder, time=time(hour=12, minute=0))

        # Создание директорий
        os.makedirs('receipts', exist_ok=True)
        os.makedirs('img', exist_ok=True)

        # Запуск бота с обработкой ошибок
        logger.info("Запуск бота...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,  # Игнорируем накопившиеся обновления при запуске
            pool_timeout=30.0,  # Увеличиваем таймаут пула
            read_timeout=30.0,  # Увеличиваем таймаут чтения
            write_timeout=30.0,  # Увеличиваем таймаут записи
            connect_timeout=30.0  # Увеличиваем таймаут подключения
        )
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {str(e)}\n{traceback.format_exc()}")
        raise

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.critical(f"Фатальная ошибка: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1)
