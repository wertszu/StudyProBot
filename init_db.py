from database import init_db, User, Order, OrderStatus, Payment, PaymentStatus
from datetime import datetime, timedelta
from sqlalchemy import text

def init_test_data(session):
    """Initialize test data in the database."""
    print("Creating test data...")
    
    # Create test user
    user = User(
        telegram_id=5615980623,  # Замените на ваш реальный telegram_id
        username="test_user",
        first_name="Test",
        last_name="User"
    )
    session.add(user)
    session.commit()
    print(f"Created test user with ID: {user.id}")
    
    # Create test order
    order = Order(
        user_id=user.id,
        work_type="coursework",
        subject="Test Subject",
        volume="25 pages",
        deadline=datetime.now() + timedelta(days=7),
        status=OrderStatus.PENDING,
        price=0,
        contact_info="test@example.com",
        created_at=datetime.now()
    )
    session.add(order)
    session.commit()
    print(f"Created test order with ID: {order.id}")
    
    print("Test data created successfully!")

if __name__ == "__main__":
    print("Инициализация базы данных...")
    session = init_db()
    
    # Проверяем создание таблиц
    print("\nПроверка таблиц:")
    for table in session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall():
        print(f"- {table[0]}")
    
    # Создаем тестовые данные
    init_test_data(session)
    
    print("\nБаза данных успешно создана!") 