from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import Order, OrderStatus, User, Payment, PaymentStatus, Message, Review
from datetime import datetime, timedelta
from sqlalchemy import func
import logging
from states import (
    WAITING_BROADCAST,
    WAITING_REVIEW_RESPONSE,
    WAITING_USER_MESSAGE,
    WAITING_PRICE
)

# Настройка логгера
logger = logging.getLogger(__name__)

# Константы
ORDER_STATUS_MESSAGES = {
    OrderStatus.PENDING: "⏳ Ожидает оплаты",
    OrderStatus.PAID: "💰 Оплачен",
    OrderStatus.IN_PROGRESS: "⚙️ В работе",
    OrderStatus.COMPLETED: "✅ Выполнен",
    OrderStatus.CANCELLED: "❌ Отменен"
}

def get_admin_keyboard():
    """Возвращает клавиатуру админ-панели."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Новые заказы", callback_data='admin_new_orders')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("📢 Рассылка", callback_data='admin_broadcast')],
        [InlineKeyboardButton("⭐ Отзывы", callback_data='admin_reviews')],
        [InlineKeyboardButton("📨 Сообщения", callback_data='admin_messages')]
    ])

def get_order_keyboard(order_id: int):
    """Возвращает клавиатуру для управления заказом."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принять", callback_data=f'admin_accept_{order_id}'),
            InlineKeyboardButton("❌ Отклонить", callback_data=f'admin_reject_{order_id}')
        ],
        [InlineKeyboardButton("💬 Написать", callback_data=f'admin_message_{order_id}')]
    ])

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel."""
    if update.effective_user.id != context.bot_data['admin_id']:
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "👨‍💼 Панель администратора\n\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END

async def admin_new_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show new orders."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    session = context.bot_data['db_session']
    new_orders = session.query(Order).filter_by(status=OrderStatus.PENDING).all()
    
    logger.info(f"Found {len(new_orders)} new orders")
    
    if not new_orders:
        await query.message.reply_text(
            "📭 Новых заказов нет.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END
    
    for order in new_orders:
        user = session.query(User).filter_by(id=order.user_id).first()
        logger.info(f"Processing order #{order.id} for user {user.telegram_id if user else 'Unknown'}")
        
        if not user:
            logger.error(f"User not found for order #{order.id}")
            continue
            
        message = (
            f"🆕 Новый заказ #{order.id}\n"
            f"👤 От: {user.first_name}\n"
            f"📚 Тип: {order.work_type}\n"
            f"📝 Предмет: {order.subject}\n"
            f"📊 Объём: {order.volume}\n"
            f"⏰ Дедлайн: {order.deadline.strftime('%d.%m.%Y')}\n"
            f"💰 Цена: {order.price} ₽\n"
            f"📞 Контакты: {order.contact_info}\n"
            f"💬 Комментарий: {order.comment or 'Нет'}"
        )
        
        await query.message.reply_text(
            message,
            reply_markup=get_order_keyboard(order.id)
        )
    
    await query.message.reply_text(
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END

async def admin_accept_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Accept order and set price."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    order_id = int(query.data.split('_')[2])
    session = context.bot_data['db_session']
    
    try:
        logger.info(f"Accepting order #{order_id}")
        
        order = session.query(Order).filter_by(id=order_id).first()
        if not order:
            logger.error(f"Order #{order_id} not found")
            await query.message.reply_text("❌ Заказ не найден.")
            return ConversationHandler.END
        
        # Store order_id in context for price setting
        context.user_data['current_order_id'] = order_id
        logger.info(f"Stored order #{order_id} in context for price setting")
        
        await query.message.reply_text(
            f"💰 Установите цену для заказа #{order_id} (в рублях):"
        )
        return WAITING_PRICE
        
    except Exception as e:
        logger.error(f"Error accepting order: {str(e)}", exc_info=True)
        session.rollback()
        await query.message.reply_text(
            f"❌ Произошла ошибка при принятии заказа.\n"
            f"Ошибка: {str(e)}",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def handle_price_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price setting by admin."""
    if update.effective_user.id != context.bot_data['admin_id']:
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    if 'current_order_id' not in context.user_data:
        await update.message.reply_text(
            "❌ Ошибка: заказ не найден.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END
    
    try:
        price = float(update.message.text)
        if price <= 0:
            await update.message.reply_text(
                "❌ Цена должна быть больше нуля. Попробуйте еще раз:"
            )
            return WAITING_PRICE
        
        order_id = context.user_data['current_order_id']
        session = context.bot_data['db_session']
        
        logger.info(f"Setting price for order #{order_id}")
        
        # Проверяем существование заказа
        order = session.query(Order).filter_by(id=order_id).first()
        if not order:
            logger.error(f"Order #{order_id} not found")
            await update.message.reply_text(
                "❌ Заказ не найден.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END
        
        # Проверяем существование пользователя
        user = session.query(User).filter_by(id=order.user_id).first()
        if not user:
            logger.error(f"User not found for order #{order_id}")
            await update.message.reply_text(
                "❌ Пользователь не найден.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END
        
        logger.info(f"Found user: {user.telegram_id} for order #{order_id}")
        logger.info(f"User details - ID: {user.id}, Telegram ID: {user.telegram_id}, Name: {user.first_name}")
        
        # Отправляем уведомление пользователю
        keyboard = [[InlineKeyboardButton("Оплатить", callback_data=f'pay_{order.id}')]]
        try:
            logger.info(f"Attempting to send notification to user {user.telegram_id}")
            
            # Проверяем, что telegram_id не None
            if not user.telegram_id:
                raise ValueError("User telegram_id is None")
            
            notification_text = (
                f"✅ Ваш заказ #{order.id} принят!\n"
                f"💰 Стоимость: {price} ₽\n"
                "Для подтверждения заказа — перейдите к оплате:"
            )
            
            logger.info(f"Sending message to user {user.telegram_id} with text: {notification_text}")
            
            # Отправляем сообщение пользователю
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=notification_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"Notification sent successfully to user {user.telegram_id}")
            
            # Только после успешной отправки сообщения обновляем цену в базе данных
            order.price = price
            session.commit()
            logger.info(f"Updated order #{order_id} with price {price}")
            
            # Отправляем подтверждение админу
            await update.message.reply_text(
                f"✅ Цена установлена: {price} ₽\n"
                f"Пользователь уведомлен о стоимости.",
                reply_markup=get_admin_keyboard()
            )
            
            # Очищаем текущий заказ из контекста только после успешной отправки
            del context.user_data['current_order_id']
            logger.info(f"Cleared order #{order_id} from context")
            
        except Exception as e:
            logger.error(f"Error sending notification to user {user.telegram_id}: {str(e)}", exc_info=True)
            error_message = (
                f"❌ Не удалось отправить уведомление пользователю.\n"
                f"Ошибка: {str(e)}\n"
                f"telegram_id пользователя: {user.telegram_id}"
            )
            await update.message.reply_text(
                error_message,
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректную сумму:"
        )
        return WAITING_PRICE
    except Exception as e:
        logger.error(f"Error setting price: {str(e)}", exc_info=True)
        session.rollback()
        await update.message.reply_text(
            f"❌ Произошла ошибка при установке цены.\n"
            f"Ошибка: {str(e)}",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def admin_reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject order."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    order_id = int(query.data.split('_')[2])
    session = context.bot_data['db_session']
    
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order:
            await query.message.reply_text("❌ Заказ не найден.")
            return ConversationHandler.END
        
        order.status = OrderStatus.CANCELLED
        session.commit()
        
        # Notify user
        user = session.query(User).filter_by(id=order.user_id).first()
        await context.bot.send_message(
            chat_id=user.telegram_id,
            text=f"❌ Ваш заказ #{order.id} отклонен."
        )
        
        await query.message.reply_text(
            f"❌ Заказ #{order_id} отклонен.",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error rejecting order: {str(e)}", exc_info=True)
        session.rollback()
        await query.message.reply_text(
            "❌ Произошла ошибка при отклонении заказа.",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    session = context.bot_data['db_session']
    
    try:
        # Get total orders
        total_orders = session.query(Order).count()
        
        # Get orders by status
        orders_by_status = {}
        for status in OrderStatus:
            count = session.query(Order).filter_by(status=status).count()
            orders_by_status[status] = count
        
        # Get total users
        total_users = session.query(User).count()
        
        # Get total revenue
        total_revenue = session.query(Payment).filter_by(status=PaymentStatus.COMPLETED).with_entities(func.sum(Payment.amount)).scalar() or 0
        
        message = (
            "📊 Статистика\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"📦 Всего заказов: {total_orders}\n"
            f"💰 Общая выручка: {total_revenue} ₽\n\n"
            "📈 Заказы по статусам:\n"
        )
        
        for status, count in orders_by_status.items():
            message += f"{ORDER_STATUS_MESSAGES[status]}: {count}\n"
        
        await query.message.reply_text(
            message,
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}", exc_info=True)
        await query.message.reply_text(
            "❌ Произошла ошибка при получении статистики.",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast process."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    await query.message.reply_text(
        "📢 Введите сообщение для рассылки:"
    )
    return WAITING_BROADCAST

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message."""
    if update.effective_user.id != context.bot_data['admin_id']:
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    message = update.message.text
    session = context.bot_data['db_session']
    
    try:
        users = session.query(User).all()
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=message
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Error sending broadcast to user {user.telegram_id}: {str(e)}")
                failed_count += 1
        
        await update.message.reply_text(
            f"✅ Рассылка завершена\n"
            f"📤 Успешно отправлено: {sent_count}\n"
            f"❌ Ошибок: {failed_count}",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error during broadcast: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка при рассылке.",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def admin_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reviews."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    session = context.bot_data['db_session']
    
    try:
        reviews = session.query(Review).order_by(Review.created_at.desc()).all()
        
        if not reviews:
            await query.message.reply_text(
                "📭 Отзывов пока нет.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END
        
        for review in reviews:
            user = session.query(User).filter_by(id=review.user_id).first()
            message = (
                f"⭐ Отзыв от {user.first_name} (@{user.username})\n"
                f"📅 {review.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"📝 {review.text}\n"
                f"💬 Ответ: {review.admin_response or 'Нет ответа'}"
            )
            
            keyboard = [[InlineKeyboardButton("💬 Ответить", callback_data=f'admin_review_response_{review.id}')]]
            await query.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        await query.message.reply_text(
            "Выберите действие:",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error getting reviews: {str(e)}", exc_info=True)
        await query.message.reply_text(
            "❌ Произошла ошибка при получении отзывов.",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def admin_review_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start review response process."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    review_id = int(query.data.split('_')[3])
    context.user_data['review_id'] = review_id
    
    await query.message.reply_text(
        "💬 Введите ответ на отзыв:"
    )
    return WAITING_REVIEW_RESPONSE

async def handle_review_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle review response."""
    if update.effective_user.id != context.bot_data['admin_id']:
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    if 'review_id' not in context.user_data:
        await update.message.reply_text(
            "❌ Ошибка: отзыв не найден.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END
    
    review_id = context.user_data['review_id']
    response = update.message.text
    session = context.bot_data['db_session']
    
    try:
        review = session.query(Review).filter_by(id=review_id).first()
        if not review:
            await update.message.reply_text(
                "❌ Отзыв не найден.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END
        
        review.admin_response = response
        session.commit()
        
        # Notify user
        user = session.query(User).filter_by(id=review.user_id).first()
        await context.bot.send_message(
            chat_id=user.telegram_id,
            text=f"💬 Администратор ответил на ваш отзыв:\n\n{response}"
        )
        
        await update.message.reply_text(
            "✅ Ответ на отзыв сохранен.",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error saving review response: {str(e)}", exc_info=True)
        session.rollback()
        await update.message.reply_text(
            "❌ Произошла ошибка при сохранении ответа.",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show messages."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    session = context.bot_data['db_session']
    
    try:
        messages = session.query(Message).order_by(Message.created_at.desc()).all()
        
        if not messages:
            await query.message.reply_text(
                "📭 Сообщений пока нет.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END
        
        for message in messages:
            user = session.query(User).filter_by(id=message.user_id).first()
            message_text = (
                f"📨 Сообщение от {user.first_name} (@{user.username})\n"
                f"📅 {message.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"📝 {message.text}\n"
                f"💬 Ответ: {message.admin_response or 'Нет ответа'}"
            )
            
            keyboard = [[InlineKeyboardButton("💬 Ответить", callback_data=f'admin_message_response_{message.id}')]]
            await query.message.reply_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        await query.message.reply_text(
            "Выберите действие:",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}", exc_info=True)
        await query.message.reply_text(
            "❌ Произошла ошибка при получении сообщений.",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def admin_message_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start message response process."""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != context.bot_data['admin_id']:
        await query.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    message_id = int(query.data.split('_')[3])
    context.user_data['message_id'] = message_id
    
    await query.message.reply_text(
        "💬 Введите ответ на сообщение:"
    )
    return WAITING_USER_MESSAGE

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user message response."""
    if update.effective_user.id != context.bot_data['admin_id']:
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    
    if 'message_id' not in context.user_data:
        await update.message.reply_text(
            "❌ Ошибка: сообщение не найдено.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END
    
    message_id = context.user_data['message_id']
    response = update.message.text
    session = context.bot_data['db_session']
    
    try:
        message = session.query(Message).filter_by(id=message_id).first()
        if not message:
            await update.message.reply_text(
                "❌ Сообщение не найдено.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END
        
        message.admin_response = response
        session.commit()
        
        # Notify user
        user = session.query(User).filter_by(id=message.user_id).first()
        await context.bot.send_message(
            chat_id=user.telegram_id,
            text=f"💬 Администратор ответил на ваше сообщение:\n\n{response}"
        )
        
        await update.message.reply_text(
            "✅ Ответ на сообщение сохранен.",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error saving message response: {str(e)}", exc_info=True)
        session.rollback()
        await update.message.reply_text(
            "❌ Произошла ошибка при сохранении ответа.",
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END 