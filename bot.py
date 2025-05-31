import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)
from dotenv import load_dotenv
from sqlalchemy import text
from functools import lru_cache

# Загрузка переменных окружения
load_dotenv()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Отладочная информация
logger.info(f"ADMIN_ID from env: {os.getenv('ADMIN_ID')}")
logger.info(f"TELEGRAM_TOKEN from env: {os.getenv('TELEGRAM_TOKEN')}")

# Модули проекта
from database import init_db, Order, OrderStatus, User, Message, Review, Payment, PaymentStatus
from states import (
    WAITING_WORK_TYPE,
    WAITING_SUBJECT,
    WAITING_VOLUME,
    WAITING_DEADLINE,
    WAITING_FILE,
    WAITING_COMMENT,
    WAITING_CONTACT,
    WAITING_BROADCAST,
    WAITING_REVIEW_RESPONSE,
    WAITING_USER_MESSAGE,
    WAITING_PRICE,
    WAITING_PAYMENT_PROOF
)
from admin import (
    admin_panel, admin_stats, admin_new_orders, admin_accept_order,
    admin_reject_order, admin_broadcast, handle_broadcast,
    admin_reviews, admin_review_response, handle_review_response,
    admin_messages, admin_message_response, handle_user_message,
    handle_price_setting
)

# Константы
BASE_PRICES = {
    'coursework': 1000,
    'essay': 500,
    'control': 700,
    'translation': 150,
    'presentation': 300,
    'diploma': 3000,
    'tasks': 400
}

# Кэшируем базовые цены
@lru_cache(maxsize=128)
def get_base_price(work_type: str) -> float:
    return BASE_PRICES.get(work_type, 0)

class OrderState:
    def __init__(self):
        self.work_type = None
        self.subject = None
        self.volume = None
        self.deadline = None
        self.file_path = None
        self.comment = None
        self.contact_info = None

    def is_valid(self) -> bool:
        """Проверяет валидность состояния заказа."""
        return all([
            self.work_type,
            self.subject,
            self.volume,
            self.deadline,
            self.contact_info
        ])

def get_main_keyboard():
    """Возвращает основную клавиатуру."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Создать заказ", callback_data='create_order')],
        [InlineKeyboardButton("💰 Цены", callback_data='price')],
        [InlineKeyboardButton("📦 Мои заказы", callback_data='orders')],
        [InlineKeyboardButton("💬 Поддержка", callback_data='support')],
        [InlineKeyboardButton("⭐ Отзывы", callback_data='reviews')]
    ])

def get_cancel_keyboard():
    """Возвращает клавиатуру с кнопкой отмены."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data='cancel')]])

async def choose_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle work type selection."""
    try:
        # Обработка callback_query
        if update.callback_query:
            await update.callback_query.answer()
            message = update.callback_query.message
        else:
            message = update.message

        keyboard = [
            [
                InlineKeyboardButton("📚 Курсовая", callback_data='work_type_coursework'),
                InlineKeyboardButton("📝 Реферат", callback_data='work_type_essay')
            ],
            [
                InlineKeyboardButton("📐 Контрольная", callback_data='work_type_control'),
                InlineKeyboardButton("💡 Перевод", callback_data='work_type_translation')
            ],
            [
                InlineKeyboardButton("🎓 Презентация", callback_data='work_type_presentation'),
                InlineKeyboardButton("👨‍🏫 Диплом", callback_data='work_type_diploma')
            ],
            [InlineKeyboardButton("📋 Задачи", callback_data='work_type_tasks')],
            [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
        ]
        
        if update.callback_query:
            await message.edit_text(
                "Выберите тип работы:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await message.reply_text(
                "Выберите тип работы:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return WAITING_WORK_TYPE
        
    except Exception as e:
        logger.error(f"Error in choose_work_type: {str(e)}", exc_info=True)
        error_message = "Произошла ошибка. Пожалуйста, попробуйте позже."
        if update.callback_query:
            await update.callback_query.message.reply_text(error_message)
        else:
            await update.message.reply_text(error_message)
        return ConversationHandler.END

async def handle_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle work type selection."""
    try:
        query = update.callback_query
        await query.answer()
        
        work_type = query.data.replace('work_type_', '')
        context.user_data['order_state'] = OrderState()
        context.user_data['order_state'].work_type = work_type
        
        message = (
            f"📚 {work_type.capitalize()}\n\n"
            "Пожалуйста, укажите:\n"
            "1. Предмет/дисциплину\n"
            "2. Тему работы\n"
            "3. Краткое описание задания\n\n"
            "Например:\n"
            "Предмет: Экономика\n"
            "Тема: Анализ эффективности инвестиционных проектов\n"
            "Описание: Необходимо провести анализ трех инвестиционных проектов..."
        )
        
        await query.message.edit_text(
            message,
            reply_markup=get_cancel_keyboard()
        )
        
        return WAITING_SUBJECT
        
    except Exception as e:
        logger.error(f"Error in handle_work_type: {str(e)}", exc_info=True)
        await update.callback_query.message.reply_text(
            "❌ Произошла ошибка при выборе типа работы. Пожалуйста, попробуйте позже.",
            reply_markup=get_cancel_keyboard()
        )
        return ConversationHandler.END

async def handle_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subject input."""
    try:
        if 'order_state' not in context.user_data:
            await update.message.reply_text(
                "❌ Произошла ошибка. Пожалуйста, начните заказ заново.",
                reply_markup=get_cancel_keyboard()
            )
            return ConversationHandler.END
        
        subject = update.message.text.strip()
        if len(subject) < 3:
            await update.message.reply_text(
                "❌ Слишком короткое описание. Пожалуйста, укажите более подробно:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_SUBJECT
        
        context.user_data['order_state'].subject = subject
        
        work_type = context.user_data['order_state'].work_type
        volume_message = {
            'coursework': "Укажите количество страниц (обычно 25-35):",
            'essay': "Укажите количество страниц (обычно 10-15):",
            'control': "Укажите количество задач:",
            'translation': "Укажите количество знаков или страниц:",
            'presentation': "Укажите количество слайдов:",
            'diploma': "Укажите количество страниц (обычно 60-80):",
            'tasks': "Укажите количество задач:"
        }.get(work_type, "Укажите объём работы:")
        
        await update.message.reply_text(
            volume_message,
            reply_markup=get_cancel_keyboard()
        )
        
        return WAITING_VOLUME
        
    except Exception as e:
        logger.error(f"Error in handle_subject: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_cancel_keyboard()
        )
        return ConversationHandler.END

async def handle_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle volume input."""
    if 'order_state' not in context.user_data:
        context.user_data['order_state'] = OrderState()
    
    volume = update.message.text.strip()
    if not volume.replace('.', '').isdigit():
        await update.message.reply_text(
            "❌ Пожалуйста, укажите числовое значение:",
            reply_markup=get_cancel_keyboard()
        )
        return WAITING_VOLUME
    
    context.user_data['order_state'].volume = volume
    await update.message.reply_text(
        "Укажите дедлайн в формате ДД.ММ.ГГГГ (например: 01.01.2025):",
        reply_markup=get_cancel_keyboard()
    )
    return WAITING_DEADLINE

async def handle_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deadline input."""
    if 'order_state' not in context.user_data:
        context.user_data['order_state'] = OrderState()
    
    try:
        deadline = datetime.strptime(update.message.text.strip(), "%d.%m.%Y")
        
        if deadline < datetime.now():
            await update.message.reply_text(
                "❌ Дата не может быть в прошлом. Пожалуйста, укажите будущую дату:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_DEADLINE
        
        max_deadline = datetime.now() + timedelta(days=365)
        if deadline > max_deadline:
            await update.message.reply_text(
                "❌ Слишком далекий дедлайн. Пожалуйста, укажите дату в пределах года:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_DEADLINE
        
        context.user_data['order_state'].deadline = deadline
        
        await update.message.reply_text(
            "Отправьте файл с заданием (поддерживаются фото, PDF, DOCX):",
            reply_markup=get_cancel_keyboard()
        )
        return WAITING_FILE
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, используйте формат ДД.ММ.ГГГГ:",
            reply_markup=get_cancel_keyboard()
        )
        return WAITING_DEADLINE

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file upload."""
    logger.info("handle_file called")
    
    if 'order_state' not in context.user_data:
        logger.info("Creating new order state")
        context.user_data['order_state'] = OrderState()
    
    try:
        # Проверяем наличие файла или фото
        if update.message.document:
            logger.info(f"Received document: {update.message.document.file_name}")
            file = update.message.document
            file_ext = file.file_name.split('.')[-1].lower()
            if file_ext not in ['pdf', 'docx', 'doc']:
                await update.message.reply_text(
                    "❌ Поддерживаются только файлы PDF и DOCX. Пожалуйста, отправьте файл в правильном формате.",
                    reply_markup=get_cancel_keyboard()
                )
                return WAITING_FILE
        elif update.message.photo:
            logger.info("Received photo")
            file = update.message.photo[-1]  # Берем фото с максимальным разрешением
        else:
            logger.info("No file or photo received")
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте файл (PDF, DOCX) или фото.",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_FILE

        # Создаем директорию для файлов, если её нет
        files_dir = os.path.join(os.getcwd(), 'files')
        if not os.path.exists(files_dir):
            logger.info(f"Creating directory: {files_dir}")
            try:
                os.makedirs(files_dir)
            except Exception as e:
                logger.error(f"Error creating directory: {str(e)}")
                raise

        # Генерируем уникальное имя файла
        file_id = file.file_id
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if update.message.document:
            file_name = f"{timestamp}_{file_id}_{file.file_name}"
        else:
            file_name = f"{timestamp}_{file_id}.jpg"
        
        file_path = os.path.join(files_dir, file_name)
        logger.info(f"Attempting to save file to: {file_path}")

        # Скачиваем файл
        try:
            # Получаем информацию о файле
            file_info = await context.bot.get_file(file_id)
            # Скачиваем файл
            await file_info.download_to_drive(file_path)
            
            # Проверяем, что файл действительно создался
            if not os.path.exists(file_path):
                raise Exception("File was not created after download")
                
            logger.info(f"File successfully saved to: {file_path}")
            
            # Сохраняем путь к файлу
            context.user_data['order_state'].file_path = file_path
            
            await update.message.reply_text(
                "✅ Файл успешно загружен!\n\n"
                "Добавьте комментарий к заказу (или отправьте '-' если комментария нет):",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_COMMENT
            
        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}")
            # Пытаемся удалить файл, если он был частично создан
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            raise
        
    except Exception as e:
        logger.error(f"Error handling file: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка при сохранении файла. Пожалуйста, попробуйте еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        return WAITING_FILE

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle comment input."""
    if 'order_state' not in context.user_data:
        context.user_data['order_state'] = OrderState()
    
    comment = update.message.text.strip()
    if comment == '-':
        comment = None
    
    context.user_data['order_state'].comment = comment
    
    await update.message.reply_text(
        "Отправьте контактную информацию (телефон или email):",
        reply_markup=get_cancel_keyboard()
    )
    return WAITING_CONTACT

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contact info and finalize order."""
    if 'order_state' not in context.user_data:
        await update.message.reply_text(
            "❌ Ошибка: данные заказа не найдены.",
            reply_markup=get_cancel_keyboard()
        )
        return ConversationHandler.END
    
    order_state = context.user_data['order_state']
    order_state.contact_info = update.message.text.strip()
    
    if not order_state.is_valid():
        await update.message.reply_text(
            "❌ Ошибка: не все данные заказа заполнены.",
            reply_markup=get_cancel_keyboard()
        )
        return ConversationHandler.END
    
    session = context.bot_data['db_session']
    
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user:
            user = User(
                telegram_id=update.effective_user.id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name
            )
            session.add(user)
            session.commit()
        
        order = Order(
            user_id=user.id,
            work_type=order_state.work_type,
            subject=order_state.subject,
            volume=order_state.volume,
            deadline=order_state.deadline,
            status=OrderStatus.PENDING,
            price=get_base_price(order_state.work_type),
            file_path=order_state.file_path,
            comment=order_state.comment,
            contact_info=order_state.contact_info
        )
        
        session.add(order)
        session.commit()
        
        await update.message.reply_text(
            f"✅ Заказ #{order.id} успешно создан!\n\n"
            f"📚 Тип: {order.work_type}\n"
            f"📝 Предмет: {order.subject}\n"
            f"📊 Объём: {order.volume}\n"
            f"⏰ Дедлайн: {order.deadline.strftime('%d.%m.%Y')}\n\n"
            "Администратор рассмотрит ваш заказ и установит точную стоимость."
        )
        
        admin_message = (
            f"🆕 Новый заказ #{order.id}\n"
            f"👤 От: {user.first_name}\n"
            f"📚 Тип: {order.work_type}\n"
            f"📝 Предмет: {order.subject}\n"
            f"📊 Объём: {order.volume}\n"
            f"⏰ Дедлайн: {order.deadline.strftime('%d.%m.%Y')}\n"
            f"💰 Базовая цена: {order.price} ₽\n"
            f"📞 Контакты: {order.contact_info}\n"
            f"💬 Комментарий: {order.comment or 'Нет'}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Принять", callback_data=f'admin_accept_{order.id}'),
                InlineKeyboardButton("❌ Отклонить", callback_data=f'admin_reject_{order.id}')
            ],
            [InlineKeyboardButton("💬 Написать", callback_data=f'admin_message_{order.id}')]
        ]
        
        await context.bot.send_message(
            chat_id=context.bot_data['admin_id'],
            text=admin_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        del context.user_data['order_state']
        
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}", exc_info=True)
        session.rollback()
        await update.message.reply_text(
            "❌ Произошла ошибка при создании заказа. Пожалуйста, попробуйте позже."
        )
    
    return ConversationHandler.END

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel order creation."""
    query = update.callback_query
    await query.answer()
    
    if 'order_state' in context.user_data:
        if context.user_data['order_state'].file_path and os.path.exists(context.user_data['order_state'].file_path):
            try:
                os.remove(context.user_data['order_state'].file_path)
            except Exception as e:
                logger.error(f"Error deleting file: {str(e)}", exc_info=True)
        
        del context.user_data['order_state']
    
    await query.message.reply_text(
        "❌ Создание заказа отменено.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data='back')
        ]])
    )
    return ConversationHandler.END

# ===== Функции-обработчики =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    try:
        text = (
            'Привет! Я — бот, который помогает студентам с:\n'
            '📚 Курсовыми\n📝 Рефератами\n📐 Контрольными\n'
            '💡 Презентациями\n🎓 Дипломами\n👨‍🏫 Задачами\n\n'
            'Выберите, что вам нужно:'
        )
        
        if update.message:
            await update.message.reply_text(text, reply_markup=get_main_keyboard())
        else:
            await update.callback_query.answer()
            await update.callback_query.message.edit_text(text, reply_markup=get_main_keyboard())
            
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}", exc_info=True)
        error_message = "Произошла ошибка. Пожалуйста, попробуйте позже."
        if update.message:
            await update.message.reply_text(error_message)
        else:
            await update.callback_query.message.reply_text(error_message)

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show price list."""
    try:
        await update.callback_query.answer()
        text = (
            '💵 Минимальные цены:\n'
            '— Курсовая: от 1000 ₽\n'
            '— Реферат: от 500 ₽\n'
            '— Контрольная: от 700 ₽\n'
            '— Перевод: от 150 ₽/1800 знаков\n'
            '— Презентация: от 300 ₽\n'
            '— Дипломная: от 3000 ₽\n\n'
            '*Цена зависит от срока, сложности и объёма*'
        )
        keyboard = [[InlineKeyboardButton('◀️ Назад', callback_data='back')]]
        reply = InlineKeyboardMarkup(keyboard)
        await update.callback_query.message.edit_text(text, parse_mode='Markdown', reply_markup=reply)
        
    except Exception as e:
        logger.error(f"Error in price command: {str(e)}", exc_info=True)
        await update.callback_query.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's orders."""
    try:
        session = context.bot_data['db_session']
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        await update.callback_query.answer()
        
        keyboard = [[InlineKeyboardButton('◀️ Назад', callback_data='back')]]
        reply = InlineKeyboardMarkup(keyboard)
        
        if not user:
            return await update.callback_query.message.edit_text(
                'У вас пока нет заказов.',
                reply_markup=reply
            )
            
        orders = session.query(Order).filter_by(user_id=user.id).all()
        if not orders:
            return await update.callback_query.message.edit_text(
                'У вас пока нет заказов.',
                reply_markup=reply
            )
            
        text = '📥 Ваши заказы:\n\n'
        for o in orders:
            emoji = {
                OrderStatus.PENDING: '⏳',
                OrderStatus.PAID: '💰',
                OrderStatus.IN_PROGRESS: '🔄',
                OrderStatus.COMPLETED: '✅',
                OrderStatus.CANCELLED: '❌'
            }.get(o.status, '❓')
            text += f"{emoji} Заказ #{o.id}\nТип: {o.work_type}\nЦена: {o.price} ₽\n\n"
            
        await update.callback_query.message.edit_text(text, reply_markup=reply)
        
    except Exception as e:
        logger.error(f"Error in orders command: {str(e)}", exc_info=True)
        await update.callback_query.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle support request."""
    try:
        await update.callback_query.answer()
        keyboard = [[InlineKeyboardButton('◀️ Назад', callback_data='back')]]
        reply = InlineKeyboardMarkup(keyboard)
        await update.callback_query.message.edit_text(
            '📞 Напишите свой вопрос, и мы ответим в течение 15–60 минут.\nПо срочным вопросам: @nocent_k  @wertszus',
            reply_markup=reply
        )
        context.user_data['waiting_for_support'] = True
        return WAITING_USER_MESSAGE
        
    except Exception as e:
        logger.error(f"Error in support command: {str(e)}", exc_info=True)
        await update.callback_query.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

async def reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reviews."""
    try:
        session = context.bot_data['db_session']
        recent = session.query(Review).order_by(Review.created_at.desc()).limit(5).all()
        await update.callback_query.answer()
        
        keyboard = [[InlineKeyboardButton('◀️ Назад', callback_data='back')]]
        reply = InlineKeyboardMarkup(keyboard)
        
        text = '📢 Последние отзывы:\n\n'
        for r in recent:
            u = session.query(User).filter_by(id=r.user_id).first()
            text += f"\"{r.text}\"\n— {u.first_name if u else '-'}\n\n"
        text += 'Хотите оставить отзыв? Напишите его в чат.'
        
        await update.callback_query.message.edit_text(text, reply_markup=reply)
        return 'waiting_review'
        
    except Exception as e:
        logger.error(f"Error in reviews command: {str(e)}", exc_info=True)
        await update.callback_query.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button."""
    try:
        await update.callback_query.answer()
        text = (
            'Привет! Я — бот, который помогает студентам с:\n'
            '📚 Курсовыми\n📝 Рефератами\n📐 Контрольными\n'
            '💡 Презентациями\n🎓 Дипломами\n👨‍🏫 Задачами\n\n'
            'Выберите, что вам нужно:'
        )
        await update.callback_query.message.edit_text(text, reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Error in go_back: {str(e)}", exc_info=True)
        await update.callback_query.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle support messages from users."""
    try:
        # Проверяем, является ли пользователь администратором
        if update.effective_user.id == context.bot_data['admin_id']:
            return
            
        # Проверяем, находится ли пользователь в процессе создания заказа
        # или администратор устанавливает цену
        if 'order_state' in context.user_data or context.user_data.get('current_order_id'):
            return
        
        session = context.bot_data['db_session']
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user:
            user = User(
                telegram_id=update.effective_user.id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name
            )
            session.add(user)
            session.commit()
        
        # Сохраняем сообщение в базе данных
        msg = Message(
            user_id=user.id,
            text=update.message.text,
            is_read=False
        )
        session.add(msg)
        session.commit()
        
        # Отправляем сообщение администратору
        admin_message = (
            f"💬 Новое сообщение от {user.first_name} (@{user.username}):\n\n"
            f"{update.message.text}"
        )
        keyboard = [[InlineKeyboardButton("💬 Ответить", callback_data=f'message_user_{user.id}')]]
        await context.bot.send_message(
            chat_id=context.bot_data['admin_id'],
            text=admin_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        await update.message.reply_text('✅ Ваше сообщение отправлено администратору.')
        
    except Exception as e:
        logger.error(f"Error in handle_support_message: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user review."""
    try:
        session = context.bot_data['db_session']
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user:
            user = User(
                telegram_id=update.effective_user.id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name
            )
            session.add(user)
            session.commit()
            
        rev = Review(
            user_id=user.id,
            text=update.message.text
        )
        session.add(rev)
        session.commit()
        
        await update.message.reply_text('Спасибо! Ваш отзыв сохранён.')
        
    except Exception as e:
        logger.error(f"Error in handle_review: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    try:
        text = (
            "🤖 *Помощь по использованию бота*\n\n"
            "📝 *Создание заказа:*\n"
            "1. Нажмите 'Создать заказ'\n"
            "2. Выберите тип работы\n"
            "3. Укажите предмет и тему\n"
            "4. Укажите объём\n"
            "5. Укажите дедлайн\n"
            "6. Прикрепите файл с заданием\n"
            "7. Добавьте комментарий (если нужно)\n"
            "8. Укажите контактную информацию\n\n"
            "💰 *Цены:*\n"
            "— Курсовая: от 1000 ₽\n"
            "— Реферат: от 500 ₽\n"
            "— Контрольная: от 700 ₽\n"
            "— Перевод: от 150 ₽/1800 знаков\n"
            "— Презентация: от 300 ₽\n"
            "— Дипломная: от 3000 ₽\n\n"
            "💬 *Поддержка:*\n"
            "По всем вопросам обращайтесь через раздел 'Поддержка'"
        )
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Error in help_command: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

async def create_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start order creation process."""
    try:
        await update.callback_query.answer()
        
        # Инициализируем состояние заказа
        context.user_data['order_state'] = OrderState()
        
        keyboard = [
            [
                InlineKeyboardButton("📚 Курсовая", callback_data='work_type_coursework'),
                InlineKeyboardButton("📝 Реферат", callback_data='work_type_essay')
            ],
            [
                InlineKeyboardButton("📐 Контрольная", callback_data='work_type_control'),
                InlineKeyboardButton("💡 Перевод", callback_data='work_type_translation')
            ],
            [
                InlineKeyboardButton("🎓 Презентация", callback_data='work_type_presentation'),
                InlineKeyboardButton("👨‍🏫 Диплом", callback_data='work_type_diploma')
            ],
            [InlineKeyboardButton("📋 Задачи", callback_data='work_type_tasks')],
            [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
        ]
        
        await update.callback_query.message.edit_text(
            "Выберите тип работы:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_WORK_TYPE
        
    except Exception as e:
        logger.error(f"Error in create_order: {str(e)}", exc_info=True)
        await update.callback_query.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation."""
    try:
        if update.message:
            await update.message.reply_text(
                "❌ Операция отменена.",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.callback_query.answer()
            await update.callback_query.message.edit_text(
                "❌ Операция отменена.",
                reply_markup=get_main_keyboard()
            )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in cancel: {str(e)}", exc_info=True)
        if update.message:
            await update.message.reply_text(
                "Произошла ошибка. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.callback_query.message.reply_text(
                "Произошла ошибка. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_keyboard()
            )
        return ConversationHandler.END

async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment button click."""
    try:
        query = update.callback_query
        await query.answer()
        
        # Получаем ID заказа из callback_data
        order_id = int(query.data.split('_')[1])
        session = context.bot_data['db_session']
        
        # Получаем заказ
        order = session.query(Order).filter_by(id=order_id).first()
        if not order:
            await query.message.edit_text(
                "❌ Заказ не найден.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Проверяем, что заказ принадлежит пользователю
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or order.user_id != user.id:
            await query.message.edit_text(
                "❌ У вас нет доступа к этому заказу.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Проверяем статус заказа
        if order.status != OrderStatus.PENDING:
            await query.message.edit_text(
                "❌ Этот заказ уже оплачен или отменен.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Создаем платеж
        payment = Payment(
            user_id=user.id,
            order_id=order.id,
            amount=order.price,
            status=PaymentStatus.PENDING
        )
        session.add(payment)
        session.commit()
        
        # Сохраняем ID заказа в контексте
        context.user_data['current_payment_order_id'] = order.id
        
        # Отправляем сообщение с инструкциями по оплате
        payment_message = (
            f"💰 Оплата заказа #{order.id}\n\n"
            f"Сумма к оплате: {order.price} ₽\n\n"
            "Для оплаты:\n"
            f"1. Переведите {order.price} ₽ на карту:\n"
            "💳 2202 2050 0031 5959\n\n"
            "2. После оплаты отправьте фото или скриншот чека/квитанции об оплате"
        )
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data='cancel')]]
        await query.message.edit_text(
            payment_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return WAITING_PAYMENT_PROOF
        
    except Exception as e:
        logger.error(f"Error in handle_payment: {str(e)}", exc_info=True)
        await query.message.edit_text(
            "❌ Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment proof upload."""
    try:
        if 'current_payment_order_id' not in context.user_data:
            await update.message.reply_text(
                "❌ Ошибка: не найден активный платеж.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
        
        order_id = context.user_data['current_payment_order_id']
        session = context.bot_data['db_session']
        
        # Получаем заказ и пользователя
        order = session.query(Order).filter_by(id=order_id).first()
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        
        if not order or not user or order.user_id != user.id:
            await update.message.reply_text(
                "❌ Ошибка: заказ не найден или у вас нет доступа.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
        
        # Проверяем наличие файла или фото
        if update.message.photo:
            file = update.message.photo[-1]  # Берем фото с максимальным разрешением
        elif update.message.document:
            file = update.message.document
        else:
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте фото или файл с подтверждением оплаты.",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_PAYMENT_PROOF
        
        # Создаем директорию для файлов оплаты
        payments_dir = os.path.join(os.getcwd(), 'payment_proofs')
        if not os.path.exists(payments_dir):
            os.makedirs(payments_dir)
        
        # Генерируем имя файла
        file_id = file.file_id
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if update.message.document:
            file_name = f"{timestamp}_{file_id}_{file.file_name}"
        else:
            file_name = f"{timestamp}_{file_id}.jpg"
        
        file_path = os.path.join(payments_dir, file_name)
        
        # Скачиваем файл
        file_info = await context.bot.get_file(file_id)
        await file_info.download_to_drive(file_path)
        
        # Обновляем информацию о платеже
        payment = session.query(Payment).filter_by(order_id=order.id).first()
        if payment:
            payment.proof_file = file_path
            session.commit()
        
        # Отправляем подтверждение пользователю
        await update.message.reply_text(
            "✅ Подтверждение оплаты получено!\n"
            "Администратор проверит оплату и подтвердит её в ближайшее время.",
            reply_markup=get_main_keyboard()
        )
        
        # Уведомляем администратора
        admin_message = (
            f"💰 Получено подтверждение оплаты за заказ #{order.id}\n"
            f"👤 От: {user.first_name}\n"
            f"💵 Сумма: {order.price} ₽"
        )
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f'admin_confirm_payment_{order.id}'),
                InlineKeyboardButton("❌ Отклонить", callback_data=f'admin_reject_payment_{order.id}')
            ]
        ]
        await context.bot.send_photo(
            chat_id=context.bot_data['admin_id'],
            photo=file_path,
            caption=admin_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Очищаем контекст
        del context.user_data['current_payment_order_id']
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in handle_payment_proof: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке подтверждения оплаты. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def admin_confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin payment confirmation."""
    try:
        query = update.callback_query
        await query.answer()
        
        # Получаем ID заказа из callback_data
        order_id = int(query.data.split('_')[3])
        session = context.bot_data['db_session']
        
        # Получаем заказ
        order = session.query(Order).filter_by(id=order_id).first()
        if not order:
            await query.message.edit_text(
                "❌ Заказ не найден.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Обновляем статус заказа и платежа
        order.status = OrderStatus.PAID
        payment = session.query(Payment).filter_by(order_id=order.id).first()
        if payment:
            payment.status = PaymentStatus.COMPLETED
        session.commit()
        
        # Уведомляем пользователя
        user = session.query(User).filter_by(id=order.user_id).first()
        if user:
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=f"✅ Оплата заказа #{order.id} подтверждена!\n\nМы приступим к выполнению вашего заказа.",
                reply_markup=get_main_keyboard()
            )
        
        # Обновляем сообщение администратора
        await query.message.edit_caption(
            caption=f"✅ Оплата заказа #{order.id} подтверждена",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error in admin_confirm_payment: {str(e)}", exc_info=True)
        await query.message.edit_text(
            "❌ Произошла ошибка при подтверждении оплаты. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

async def admin_reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin payment rejection."""
    try:
        query = update.callback_query
        await query.answer()
        
        # Получаем ID заказа из callback_data
        order_id = int(query.data.split('_')[3])
        session = context.bot_data['db_session']
        
        # Получаем заказ
        order = session.query(Order).filter_by(id=order_id).first()
        if not order:
            await query.message.edit_text(
                "❌ Заказ не найден.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Обновляем статус платежа
        payment = session.query(Payment).filter_by(order_id=order.id).first()
        if payment:
            payment.status = PaymentStatus.REJECTED
        session.commit()
        
        # Уведомляем пользователя
        user = session.query(User).filter_by(id=order.user_id).first()
        if user:
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=f"❌ Оплата заказа #{order.id} отклонена.\n\nПожалуйста, проверьте правильность оплаты и попробуйте снова.",
                reply_markup=get_main_keyboard()
            )
        
        # Обновляем сообщение администратора
        await query.message.edit_caption(
            caption=f"❌ Оплата заказа #{order.id} отклонена",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error in admin_reject_payment: {str(e)}", exc_info=True)
        await query.message.edit_text(
            "❌ Произошла ошибка при отклонении оплаты. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

def main():
    """Start the bot."""
    try:
        # Инициализация базы данных
        db_session = init_db()
        logger.info("Database initialized successfully")
        
        # Создание приложения
        application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
        
        # Сохраняем данные в bot_data
        application.bot_data['admin_id'] = int(os.getenv('ADMIN_ID'))
        application.bot_data['db_session'] = db_session
        
        # Command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        
        # Order conversation handler
        order_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(create_order, pattern='^create_order$')],
            states={
                WAITING_WORK_TYPE: [
                    CallbackQueryHandler(handle_work_type, pattern='^work_type_'),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_work_type)
                ],
                WAITING_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_subject)],
                WAITING_VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_volume)],
                WAITING_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deadline)],
                WAITING_FILE: [
                    MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_file)
                ],
                WAITING_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
                WAITING_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contact)]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )
        application.add_handler(order_conv)
        logger.info("Order conversation handler added to application")
        
        # Callback query handlers для главного меню
        application.add_handler(CallbackQueryHandler(price, pattern='^price$'))
        application.add_handler(CallbackQueryHandler(orders, pattern='^orders$'))
        application.add_handler(CallbackQueryHandler(support, pattern='^support$'))
        application.add_handler(CallbackQueryHandler(reviews, pattern='^reviews$'))
        application.add_handler(CallbackQueryHandler(go_back, pattern='^back$'))
        
        # Admin handlers
        admin_conv = ConversationHandler(
            entry_points=[
                CommandHandler("admin", admin_panel),
                CallbackQueryHandler(admin_accept_order, pattern='^admin_accept_')
            ],
            states={
                WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast)],
                WAITING_REVIEW_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_review_response)],
                WAITING_USER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message)],
                WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price_setting)]
            },
            fallbacks=[CommandHandler("admin", admin_panel)]
        )
        application.add_handler(admin_conv)
        
        # Admin callback handlers
        application.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
        application.add_handler(CallbackQueryHandler(admin_new_orders, pattern='^admin_new_orders$'))
        application.add_handler(CallbackQueryHandler(admin_reject_order, pattern='^admin_reject_'))
        application.add_handler(CallbackQueryHandler(admin_broadcast, pattern='^admin_broadcast$'))
        application.add_handler(CallbackQueryHandler(admin_reviews, pattern='^admin_reviews$'))
        application.add_handler(CallbackQueryHandler(admin_review_response, pattern='^admin_review_response_'))
        application.add_handler(CallbackQueryHandler(admin_messages, pattern='^admin_messages$'))
        application.add_handler(CallbackQueryHandler(admin_message_response, pattern='^admin_message_response_'))
        
        # Payment handlers
        application.add_handler(CallbackQueryHandler(handle_payment, pattern='^pay_'))
        application.add_handler(MessageHandler(
            filters.PHOTO | filters.Document.ALL,
            handle_payment_proof
        ))
        application.add_handler(CallbackQueryHandler(admin_confirm_payment, pattern='^admin_confirm_payment_'))
        application.add_handler(CallbackQueryHandler(admin_reject_payment, pattern='^admin_reject_payment_'))
        
        # Общий обработчик сообщений (должен быть последним)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_support_message,
            block=False
        ))
        
        # Запуск бота
        logger.info("Starting bot...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)
    finally:
        db_session.close()

if __name__ == '__main__':
    main()
