import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from bot import Base, Payment, VPNKey
from dotenv import load_dotenv
from datetime import datetime

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Состояния для ConversationHandler
WAITING_KEY = 1

# Создание базы данных
engine = create_engine('sqlite:///vpn_keys.db')
Session = sessionmaker(bind=engine)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != os.getenv('ADMIN_ID'):
        await update.message.reply_text("❌ *У вас нет доступа к этой команде\.*", parse_mode='MarkdownV2')
        return

    keyboard = [
        [InlineKeyboardButton("📝 Показать ожидающие платежи", callback_data="show_payments")],
        [InlineKeyboardButton("🔑 Управление ключами", callback_data="manage_keys")],
        [InlineKeyboardButton("📊 Статистика ключей", callback_data="show_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👨‍💼 *Панель администратора AmegaVPN*\n\n"
        "Выберите действие:",
        parse_mode='MarkdownV2',
        reply_markup=reply_markup
    )

async def show_pending_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    pending_payments = session.query(Payment).filter_by(status='pending').all()
    
    if not pending_payments:
        await update.callback_query.message.reply_text(
            "📭 *Нет ожидающих подтверждения платежей\.*",
            parse_mode='MarkdownV2'
        )
        return

    for payment in pending_payments:
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{payment.id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{payment.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            with open(payment.receipt_path, 'rb') as photo:
                await update.callback_query.message.reply_photo(
                    photo=photo,
                    caption=f"📨 *Новый платеж*\n\n"
                           f"👤 *Пользователь:* `{payment.user_id}`\n"
                           f"🆔 *ID платежа:* `{payment.id}`\n"
                           f"📊 *Статус:* Ожидает подтверждения",
                    parse_mode='MarkdownV2',
                    reply_markup=reply_markup
                )
        except FileNotFoundError:
            await update.callback_query.message.reply_text(
                f"📨 *Новый платеж*\n\n"
                f"👤 *Пользователь:* `{payment.user_id}`\n"
                f"🆔 *ID платежа:* `{payment.id}`\n"
                f"📊 *Статус:* Ожидает подтверждения\n"
                f"❌ *Ошибка:* Чек не найден",
                parse_mode='MarkdownV2',
                reply_markup=reply_markup
            )

async def show_keys_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📋 Список всех ключей", callback_data="list_all_keys"),
            InlineKeyboardButton("➕ Добавить ключи", callback_data="add_keys")
        ],
        [
            InlineKeyboardButton("🔍 Свободные ключи", callback_data="list_free_keys"),
            InlineKeyboardButton("🔒 Использованные ключи", callback_data="list_used_keys")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text(
        "🔑 *Управление ключами VPN*\n\n"
        "Выберите действие:",
        parse_mode='MarkdownV2',
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != os.getenv('ADMIN_ID'):
        await update.callback_query.answer("У вас нет доступа к этой команде.")
        return

    query = update.callback_query
    await query.answer()

    if query.data == "show_payments":
        await show_pending_payments(update, context)
    elif query.data == "manage_keys":
        await show_keys_management(update, context)
    elif query.data == "show_stats":
        await show_keys_statistics(update, context)
    elif query.data == "list_all_keys":
        await list_all_keys(update, context)
    elif query.data == "list_free_keys":
        await list_free_keys(update, context)
    elif query.data == "list_used_keys":
        await list_used_keys(update, context)
    elif query.data.startswith("approve_") or query.data.startswith("reject_"):
        action, payment_id = query.data.split('_')
        payment_id = int(payment_id)
        await handle_payment_action(update, context, action, payment_id)

async def handle_payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, payment_id: int):
    session = Session()
    payment = session.query(Payment).filter_by(id=payment_id).first()
    
    if not payment:
        await update.callback_query.message.reply_text("❌ *Платеж не найден\.*", parse_mode='MarkdownV2')
        return

    if action == "approve":
        # Проверяем наличие свободного ключа
        available_key = session.query(VPNKey).filter_by(is_used=False).first()
        if not available_key:
            await update.callback_query.message.reply_text(
                "❌ *Ошибка\! Нет доступных ключей\.*\n"
                "Пожалуйста, добавьте новые ключи\.",
                parse_mode='MarkdownV2'
            )
            return

        # Обновляем статус платежа
        payment.status = 'approved'
        
        # Генерируем email для x-ui
        email = f"user_{payment.user_id}@amegavpn.com"
        
        # Выдаем ключ пользователю
        available_key.is_used = True
        available_key.user_id = payment.user_id
        available_key.username = payment.username
        available_key.phone = payment.phone
        # Извлекаем идентификатор для x-ui
        key = available_key.key
        identifier = key.split('#')[-1] if '#' in key else None
        if identifier and identifier.startswith('AmegaVPN-'):
            identifier = identifier[len('AmegaVPN-'):]
        available_key.xui_email = identifier
        # Извлекаем xui_id (между '://' и '@')
        xui_id = None
        try:
            xui_id = key.split('://')[1].split('@')[0]
        except Exception:
            pass
        available_key.xui_id = xui_id
        available_key.activation_date = datetime.utcnow()
        available_key.expiration_date = payment.next_payment_date
        
        session.commit()
        
        # Отправляем уведомление пользователю через основной бот
        try:
            main_bot = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
            
            # Создаем кнопку для копирования ключа
            keyboard = [[
                InlineKeyboardButton("📋 Скопировать ключ", callback_data=f"copy_{available_key.key}")
            ]]
            
            # Форматируем дату
            expiration_date = available_key.expiration_date.strftime('%d\.%m\.%Y')
            
            # Форматируем сообщение с ключом
            key_message = (
                "🎉 *Оплата подтверждена\!*\n\n"
                "🔑 *Ваш ключ VPN:*\n"
                f"`{available_key.key}`\n\n"
                "📱 *Используйте его для подключения к VPN сервису*\n\n"
                "⚠️ *Важно:*\n"
                "• Не передавайте ключ третьим лицам\n"
                "• Ключ рассчитан на *1 устройство*\n"
                "• При активации на других устройствах ключ будет заблокирован\n\n"
                f"📅 *Срок действия:* до {expiration_date}"
            )
            
            await main_bot.bot.send_message(
                chat_id=payment.user_id,
                text=key_message,
                parse_mode='MarkdownV2',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления пользователю: {e}")
            # Отправляем сообщение без кнопки в случае ошибки
            try:
                await main_bot.bot.send_message(
                    chat_id=payment.user_id,
                    text=key_message,
                    parse_mode='MarkdownV2'
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения без кнопки: {e}")

        # Форматируем дату
        expiration_date = available_key.expiration_date.strftime('%d\.%m\.%Y')
        
        # Форматируем username с @
        username = payment.username if payment.username else "Не указан"
        
        # Обновляем сообщение с платежом
        caption = (
            "📨 *Платеж обработан*\n\n"
            "👤 *Пользователь:*\n"
            f"ID: `{payment.user_id}`\n"
            f"Username: {username}\n"
            f"Телефон: `{payment.phone or 'Не указан'}`\n"
            f"📧 Email: `{email}`\n\n"
            f"🆔 *ID платежа:* `{payment.id}`\n"
            "✅ *Статус:* Подтвержден\n"
            f"🔑 *Выдан ключ:* `{available_key.key}`\n"
            f"📅 *Срок действия:* до {expiration_date}"
        )
        
        await update.callback_query.message.edit_caption(
            caption=caption,
            parse_mode='MarkdownV2'
        )
    else:
        payment.status = 'rejected'
        session.commit()
        
        # Отправляем уведомление пользователю через основной бот
        try:
            main_bot = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
            await main_bot.bot.send_message(
                chat_id=payment.user_id,
                text="❌ *Платеж отклонен\!*\n\n"
                     "Пожалуйста, проверьте правильность оплаты и попробуйте снова или обратитесь в техподдержку\.",
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления пользователю: {e}")

        # Форматируем username с @
        username = payment.username if payment.username else "Не указан"
        
        # Обновляем сообщение с платежом
        caption = (
            "📨 *Платеж обработан*\n\n"
            "👤 *Пользователь:*\n"
            f"ID: `{payment.user_id}`\n"
            f"Username: {username}\n"
            f"Телефон: `{payment.phone or 'Не указан'}`\n\n"
            f"🆔 *ID платежа:* `{payment.id}`\n"
            "❌ *Статус:* Отклонен"
        )
        
        await update.callback_query.message.edit_caption(
            caption=caption,
            parse_mode='MarkdownV2'
        )

async def list_all_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    keys = session.query(VPNKey).all()
    
    if not keys:
        await update.callback_query.message.reply_text(
            "❌ *Нет доступных ключей\.*",
            parse_mode='MarkdownV2'
        )
        return

    message = "📋 *Список всех ключей:*\n\n"
    for key in keys:
        status = "✅ Свободен" if not key.is_used else "🔒 Использован"
        message += f"🆔 *ID:* `{key.id}`\n"
        message += f"🔑 *Ключ:* `{key.key}`\n"
        message += f"📊 *Статус:* {status}\n\n"

    await update.callback_query.message.reply_text(
        message,
        parse_mode='MarkdownV2'
    )

async def list_free_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    keys = session.query(VPNKey).filter_by(is_used=False).all()
    
    if not keys:
        await update.callback_query.message.reply_text(
            "❌ *Нет свободных ключей\.*",
            parse_mode='MarkdownV2'
        )
        return

    message = "🔍 *Список свободных ключей:*\n\n"
    for key in keys:
        message += f"🆔 *ID:* `{key.id}`\n"
        message += f"🔑 *Ключ:* `{key.key}`\n\n"

    await update.callback_query.message.reply_text(
        message,
        parse_mode='MarkdownV2'
    )

async def list_used_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    keys = session.query(VPNKey).filter_by(is_used=True).all()
    
    if not keys:
        await update.callback_query.message.reply_text(
            "❌ *Нет использованных ключей\.*",
            parse_mode='MarkdownV2'
        )
        return

    message = "🔒 *Список использованных ключей:*\n\n"
    for key in keys:
        message += f"🆔 *ID:* `{key.id}`\n"
        message += f"🔑 *Ключ:* `{key.key}`\n"
        message += f"👤 *Пользователь:* `{key.user_id}`\n\n"

    await update.callback_query.message.reply_text(
        message,
        parse_mode='MarkdownV2'
    )

async def show_keys_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    total_keys = session.query(VPNKey).count()
    used_keys = session.query(VPNKey).filter_by(is_used=True).count()
    free_keys = total_keys - used_keys

    message = (
        "📊 *Статистика ключей VPN:*\n\n"
        f"📦 *Всего ключей:* `{total_keys}`\n"
        f"🔒 *Использовано:* `{used_keys}`\n"
        f"✅ *Свободно:* `{free_keys}`\n"
        f"📈 *Процент использования:* `{(used_keys/total_keys*100):.1f}%`"
    )

    await update.callback_query.message.reply_text(
        message,
        parse_mode='MarkdownV2'
    )

async def add_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "➕ *Добавление новых ключей*\n\n"
        "Пожалуйста, отправьте список ключей VPN, каждый с новой строки\.",
        parse_mode='MarkdownV2'
    )
    return WAITING_KEY

async def handle_new_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text(
            "❌ *Ошибка\!*\n"
            "Пожалуйста, отправьте список ключей\.",
            parse_mode='MarkdownV2'
        )
        return WAITING_KEY

    keys = update.message.text.strip().split('\n')
    session = Session()
    added_count = 0

    for key in keys:
        key = key.strip()
        if key:
            try:
                new_key = VPNKey(key=key, is_used=False)
                session.add(new_key)
                added_count += 1
            except Exception as e:
                logging.error(f"Ошибка при добавлении ключа {key}: {e}")

    session.commit()
    session.close()

    await update.message.reply_text(
        f"✅ *Добавлено {added_count} новых ключей\.*",
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="manage_keys")
        ]])
    )
    return ConversationHandler.END

def main():
    # Создание приложения
    application = Application.builder().token(os.getenv('ADMIN_BOT_TOKEN')).build()

    # Создание ConversationHandler для добавления ключей
    add_keys_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_keys, pattern="^add_keys$")],
        states={
            WAITING_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_keys)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_keys_handler)
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 