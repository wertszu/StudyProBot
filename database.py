from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Text, Boolean, Index
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase
from datetime import datetime
import enum
import os
import logging
from sqlalchemy import text

# Настройка логгера
logger = logging.getLogger(__name__)

# Константы
DATABASE_URL = "sqlite:///bot_new.db"
DATABASE_DIR = os.path.dirname(DATABASE_URL.replace('sqlite:///', ''))

# Создаем базовый класс для моделей
class Base(DeclarativeBase):
    pass

class OrderStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class PaymentStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), index=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    created_at = Column(DateTime, default=datetime.now, index=True)
    
    # Отношения
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")

class Order(Base):
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    work_type = Column(String(50), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    volume = Column(String(50), nullable=False)
    deadline = Column(DateTime, nullable=False, index=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, index=True)
    price = Column(Float, nullable=False)
    file_path = Column(String(255))
    comment = Column(Text)
    contact_info = Column(String(255))
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Отношения
    user = relationship("User", back_populates="orders")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")

class Payment(Base):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    payment_method = Column(String(50))
    transaction_id = Column(String(255), unique=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    proof_file = Column(String)  # Путь к файлу подтверждения оплаты
    
    # Отношения
    user = relationship("User", back_populates="payments")
    order = relationship("Order", back_populates="payments")

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    text = Column(Text, nullable=False)
    admin_response = Column(Text)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Отношения
    user = relationship("User", back_populates="messages")

class Review(Base):
    __tablename__ = 'reviews'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    text = Column(Text, nullable=False)
    rating = Column(Integer, index=True)
    admin_response = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Отношения
    user = relationship("User", back_populates="reviews")

def init_db():
    """Initialize database connection and create tables."""
    try:
        logger.info("Initializing database...")
        logger.info(f"Database URL: {DATABASE_URL}")
        
        # Create database directory if it doesn't exist
        if DATABASE_DIR and not os.path.exists(DATABASE_DIR):
            logger.info(f"Creating database directory: {DATABASE_DIR}")
            os.makedirs(DATABASE_DIR)
        
        # Create engine with optimized settings
        logger.info("Creating database engine...")
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,  # Проверка соединения перед использованием
            pool_recycle=3600,   # Переподключение каждый час
            connect_args={'check_same_thread': False}  # Разрешаем многопоточность
        )
        
        # Create tables if they don't exist
        logger.info("Creating database tables...")
        Base.metadata.create_all(engine)
        
        # Create session
        logger.info("Creating database session...")
        Session = sessionmaker(
            bind=engine,
            expire_on_commit=False,  # Предотвращаем истечение срока действия объектов после коммита
            autocommit=False,        # Явный контроль транзакций
            autoflush=False         # Отключаем автоматический flush
        )
        session = Session()
        
        # Test connection
        logger.info("Testing database connection...")
        session.execute(text("SELECT 1"))
        logger.info("Database connection successful!")
        
        return session
        
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        raise 