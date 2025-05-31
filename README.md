# Telegram Bot for Student Services

This bot helps students order various academic works and services.

## Features

- Order academic works (coursework, essays, control works, etc.)
- View price list
- Track order status
- Support chat
- Reviews system
- Admin panel for order management

## Setup

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

4. Edit `.env` file and add your:
- Telegram Bot Token (get it from @BotFather)
- Admin Telegram ID
- Payment system token (if using)

5. Initialize the database:
```bash
python -c "from database import init_db; init_db()"
```

6. Run the bot:
```bash
python bot.py
```

## Commands

- `/start` - Start the bot and show main menu
- `/price` - Show price list
- `/orders` - View your orders
- `/support` - Contact support
- `/reviews` - View and leave reviews

## Admin Commands

- `/admin` - Access admin panel
- `/stats` - View statistics
- `/broadcast` - Send message to all users

## Database Structure

The bot uses SQLite database with the following tables:
- Users
- Orders
- Payments
- Messages
- Reviews

## Contributing

Feel free to submit issues and enhancement requests! # study-helper-bot
