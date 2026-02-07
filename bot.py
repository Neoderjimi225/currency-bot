import os
import asyncio
import logging
from typing import Optional
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    logger.error("Установите переменную окружения BOT_TOKEN")
    exit(1)

class CurrencyBot:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def get_exchange_rate(self, from_currency: str, to_currency: str = "RUB") -> Optional[float]:
        await self.init_session()
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        if from_currency == to_currency:
            return 1.0
        
        url = f"https://api.exchangerate.host/convert?from={from_currency}&to={to_currency}"
        
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data.get("result", 0))
        except Exception as e:
            logger.error(f"Ошибка: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "💰 Я показываю курсы валют\n\n"
        "📈 Команды:\n"
        "/rate [ВАЛЮТА] - курс к рублю\n"
        "/rate [ИЗ] [В] - конвертация\n"
        "/help - помощь\n\n"
        "📝 Примеры:\n"
        "<code>/rate USD</code>\n"
        "<code>/rate EUR RUB</code>\n"
        "<code>/rate 100 USD EUR</code>",
        parse_mode='HTML'
    )

async def get_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /rate"""
    if not context.args:
        await update.message.reply_text(
            "❌ Используйте: /rate [валюта]\n"
            "Пример: /rate USD или /rate EUR RUB"
        )
        return
    
    bot = context.bot_data.get('currency_bot')
    if not bot:
        bot = CurrencyBot()
        context.bot_data['currency_bot'] = bot
    
    args = context.args
    amount = 1.0
    
    try:
        if len(args) == 3:
            amount = float(args[0])
            from_currency = args[1]
            to_currency = args[2]
        elif len(args) == 2:
            from_currency = args[0]
            to_currency = args[1]
        else:
            from_currency = args[0]
            to_currency = "RUB"
    except ValueError:
        from_currency = args[0]
        to_currency = "RUB" if len(args) == 1 else args[1]
    
    await update.message.reply_chat_action('typing')
    rate = await bot.get_exchange_rate(from_currency, to_currency)
    
    if rate is None:
        await update.message.reply_text(
            f"❌ Не удалось получить курс для {from_currency}"
        )
        return
    
    result = amount * rate
    
    response = (
        f"💱 КУРС ВАЛЮТ\n\n"
        f"📊 {from_currency.upper()} → {to_currency.upper()}\n"
        f"1 {from_currency.upper()} = {rate:.4f} {to_currency.upper()}\n"
    )
    
    if amount != 1.0:
        response += f"\n🧮 КОНВЕРТАЦИЯ:\n"
        response += f"{amount} {from_currency.upper()} = {result:.2f} {to_currency.upper()}\n"
    
    await update.message.reply_text(response)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "🆘 ПОМОЩЬ ПО БОТУ:\n\n"
        "/rate [ВАЛЮТА] - курс к рублю\n"
        "/rate [ИЗ] [В] - конвертация\n"
        "/rate [СУММА] [ИЗ] [В] - конвертация суммы\n\n"
        "📝 Примеры:\n"
        "<code>/rate USD</code>\n"
        "<code>/rate EUR USD</code>\n"
        "<code>/rate 100 EUR RUB</code>\n\n"
        "✅ Поддерживаются: USD, EUR, GBP, CNY, BTC, ETH и др.",
        parse_mode='HTML'
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ Произошла ошибка")

def main():
    """Основная функция запуска бота"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rate", get_rate))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("🚀 Бот запускается...")
    print("✅ Бот успешно запущен!")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
