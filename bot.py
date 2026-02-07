import os
import asyncio
import logging
import json
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)

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

# Состояния для ConversationHandler
SET_BASE_CURRENCY, SET_AMOUNT = range(2)

# Файл для хранения настроек пользователей
SETTINGS_FILE = "user_settings.json"

class CurrencyBot:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.user_settings = self.load_user_settings()
        self.rates_cache = {}
        self.cache_time = {}
        self.CACHE_DURATION = 300  # 5 минут кэширования
        
    def load_user_settings(self) -> Dict[str, Dict]:
        """Загрузка настроек пользователей из файла"""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
        return defaultdict(dict)
    
    def save_user_settings(self):
        """Сохранение настроек пользователей в файл"""
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.user_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
    
    async def init_session(self):
        """Инициализация сессии"""
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        """Закрытие сессии"""
        if self.session:
            await self.session.close()
    
    def get_user_setting(self, user_id: int, key: str, default: Any = None) -> Any:
        """Получение настройки пользователя"""
        return self.user_settings.get(str(user_id), {}).get(key, default)
    
    def set_user_setting(self, user_id: int, key: str, value: Any):
        """Установка настройки пользователя"""
        user_id_str = str(user_id)
        if user_id_str not in self.user_settings:
            self.user_settings[user_id_str] = {}
        self.user_settings[user_id_str][key] = value
        self.save_user_settings()
    
    async def get_all_currencies(self) -> Dict[str, str]:
        """Получение списка всех валют с их названиями"""
        currencies = {
            "RUB": "🇷🇺 Российский рубль",
            "USD": "🇺🇸 Доллар США",
            "EUR": "🇪🇺 Евро",
            "GBP": "🇬🇧 Британский фунт",
            "CNY": "🇨🇳 Китайский юань",
            "JPY": "🇯🇵 Японская иена",
            "TRY": "🇹🇷 Турецкая лира",
            "INR": "🇮🇳 Индийская рупия",
            "BRL": "🇧🇷 Бразильский реал",
            "CAD": "🇨🇦 Канадский доллар",
            "AUD": "🇦🇺 Австралийский доллар",
            "CHF": "🇨🇭 Швейцарский франк",
            "SGD": "🇸🇬 Сингапурский доллар",
            "HKD": "🇭🇰 Гонконгский доллар",
            "KRW": "🇰🇷 Южнокорейская вона",
            "MXN": "🇲🇽 Мексиканский песо",
            "IDR": "🇮🇩 Индонезийская рупия",
            "THB": "🇹🇭 Тайский бат",
            "SAR": "🇸🇦 Саудовский риял",
            "AED": "🇦🇪 Дирхам ОАЭ",
            "PLN": "🇵🇱 Польский злотый",
            "CZK": "🇨🇿 Чешская крона",
            "SEK": "🇸🇪 Шведская крона",
            "NOK": "🇳🇴 Норвежская крона",
            "DKK": "🇩🇰 Датская крона",
            "HUF": "🇭🇺 Венгерский форинт",
            "RON": "🇷🇴 Румынский лей",
            "ZAR": "🇿🇦 Южноафриканский рэнд",
            "MYR": "🇲🇾 Малайзийский ринггит",
            "PHP": "🇵🇭 Филиппинское песо",
            "VND": "🇻🇳 Вьетнамский донг",
            "UAH": "🇺🇦 Украинская гривна",
            "KZT": "🇰🇿 Казахстанский тенге",
            "BYN": "🇧🇾 Белорусский рубль",
            "ARS": "🇦🇷 Аргентинский песо",
            "CLP": "🇨🇱 Чилийское песо",
            "COP": "🇨🇴 Колумбийское песо",
            "PEN": "🇵🇪 Перуанский соль",
            "EGP": "🇪🇬 Египетский фунт",
            "NGN": "🇳🇬 Нигерийская найра",
            "PKR": "🇵🇰 Пакистанская рупия",
            "BDT": "🇧🇩 Бангладешская така",
            "BTC": "₿ Bitcoin",
            "ETH": "Ξ Ethereum",
            "XRP": "XRP",
            "LTC": "Ł Litecoin",
            "BCH": "₿ Bitcoin Cash",
            "XAU": "🥇 Золото (унция)",
            "XAG": "🥈 Серебро (унция)",
            "XPT": "🥉 Платина (унция)",
            "XPD": "🔩 Палладий (унция)"
        }
        return currencies
    
    async def get_exchange_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Получение курса валюты с кэшированием"""
        await self.init_session()
        
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        if from_currency == to_currency:
            return 1.0
        
        # Проверка кэша
        cache_key = f"{from_currency}_{to_currency}"
        current_time = datetime.now()
        
        if cache_key in self.rates_cache:
            cache_age = current_time - self.cache_time[cache_key]
            if cache_age.total_seconds() < self.CACHE_DURATION:
                return self.rates_cache[cache_key]
        
        # Попробуем несколько API
        api_urls = [
            f"https://api.exchangerate.host/convert?from={from_currency}&to={to_currency}",
            f"https://open.er-api.com/v6/latest/{from_currency}",
            f"https://api.frankfurter.app/latest?from={from_currency}",
            f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{from_currency.lower()}.json"
        ]
        
        for url in api_urls:
            try:
                async with self.session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Обработка разных форматов ответов
                        if "result" in data:  # exchangerate.host
                            rate = float(data["result"])
                            self.rates_cache[cache_key] = rate
                            self.cache_time[cache_key] = current_time
                            return rate
                        elif "rates" in data:  # open.er-api.com и frankfurter.app
                            rates = data.get("rates", {})
                            if to_currency in rates:
                                rate = float(rates[to_currency])
                                self.rates_cache[cache_key] = rate
                                self.cache_time[cache_key] = current_time
                                return rate
                        elif from_currency.lower() in data:  # fawazahmed0 API
                            rates = data.get(from_currency.lower(), {})
                            if to_currency.lower() in rates:
                                rate = float(rates[to_currency.lower()])
                                self.rates_cache[cache_key] = rate
                                self.cache_time[cache_key] = current_time
                                return rate
                        
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as e:
                logger.warning(f"API {url} failed: {e}")
                continue
        
        return None
    
    async def search_currency(self, query: str) -> Dict[str, str]:
        """Поиск валюты по названию или коду"""
        query = query.upper().strip()
        all_currencies = await bot.get_all_currencies()
        
        results = {}
        
        # Поиск по коду
        if query in all_currencies:
            results[query] = all_currencies[query]
        
        # Поиск по названию
        for code, name in all_currencies.items():
            if query in name.upper() or query in code:
                results[code] = name
        
        return results

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    bot = context.bot_data.get('currency_bot')
    
    if not bot:
        bot = CurrencyBot()
        context.bot_data['currency_bot'] = bot
    
    # Получаем настройки пользователя
    base_currency = bot.get_user_setting(user.id, "base_currency", "RUB")
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"💰 <b>Текущая базовая валюта:</b> {base_currency}\n\n"
        "📈 <b>Доступные команды:</b>\n"
        "/rate [ВАЛЮТА] - курс к базовой валюте\n"
        "/rate [ИЗ] [В] - конвертация между валютами\n"
        "/setbase - изменить базовую валюту\n"
        "/setamount - установить сумму по умолчанию\n"
        "/myconfig - мои настройки\n"
        "/search [НАЗВАНИЕ] - поиск валюты\n"
        "/list - список популярных валют\n"
        "/help - справка\n\n"
        "<b>Примеры:</b>\n"
        f"<code>/rate EUR</code> - курс EUR к {base_currency}\n"
        "<code>/rate BTC USD</code> - курс Bitcoin к Доллару\n"
        "<code>/rate 100 EUR RUB</code> - конвертировать 100 EUR в RUB"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    bot = context.bot_data.get('currency_bot')
    user = update.effective_user
    
    if bot:
        base_currency = bot.get_user_setting(user.id, "base_currency", "RUB")
    else:
        base_currency = "RUB"
    
    help_text = (
        f"🆘 <b>Помощь по использованию бота</b>\n\n"
        
        f"🎯 <b>Текущая базовая валюта:</b> {base_currency}\n\n"
        
        "⚙️ <b>Настройки:</b>\n"
        "/setbase - изменить базовую валюту\n"
        "/setamount - установить сумму по умолчанию\n"
        "/myconfig - показать мои настройки\n\n"
        
        "📊 <b>Получить курс:</b>\n"
        f"<code>/rate EUR</code> - курс Евро к {base_currency}\n"
        "<code>/rate BTC</code> - курс Bitcoin к базовой валюте\n"
        "<code>/rate BTC USD</code> - курс Bitcoin к Доллару\n\n"
        
        "🔄 <b>Конвертация:</b>\n"
        "<code>/rate 100 EUR RUB</code> - 100 евро в рубли\n"
        "<code>/rate 1 BTC USD</code> - 1 Bitcoin в долларах\n\n"
        
        "🔍 <b>Поиск:</b>\n"
        "<code>/search золото</code> - найти валюты с 'золото'\n"
        "<code>/search RUB</code> - информация о рубле\n\n"
        
        "📋 <b>Списки:</b>\n"
        "<code>/list</code> - популярные валюты\n"
        "<code>/list all</code> - все валюты"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def set_base_currency_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало процесса установки базовой валюты"""
    bot = context.bot_data.get('currency_bot')
    if not bot:
        bot = CurrencyBot()
        context.bot_data['currency_bot'] = bot
    
    keyboard = [
        [
            InlineKeyboardButton("🇷🇺 RUB", callback_data="SET_RUB"),
            InlineKeyboardButton("🇺🇸 USD", callback_data="SET_USD"),
            InlineKeyboardButton("🇪🇺 EUR", callback_data="SET_EUR"),
        ],
        [
            InlineKeyboardButton("🇬🇧 GBP", callback_data="SET_GBP"),
            InlineKeyboardButton("🇨🇳 CNY", callback_data="SET_CNY"),
            InlineKeyboardButton("🇯🇵 JPY", callback_data="SET_JPY"),
        ],
        [
            InlineKeyboardButton("🇨🇭 CHF", callback_data="SET_CHF"),
            InlineKeyboardButton("🇨🇦 CAD", callback_data="SET_CAD"),
            InlineKeyboardButton("🇦🇺 AUD", callback_data="SET_AUD"),
        ],
        [
            InlineKeyboardButton("🏆 BTC", callback_data="SET_BTC"),
            InlineKeyboardButton("🥇 XAU", callback_data="SET_XAU"),
            InlineKeyboardButton("📝 Ввести вручную", callback_data="SET_MANUAL"),
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "💱 <b>Выберите базовую валюту:</b>\n\n"
        "Это валюта, к которой будут показываться все курсы по умолчанию.\n"
        "Вы всегда можете указать другую валюту в команде /rate.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    return SET_BASE_CURRENCY

async def set_base_currency_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора базовой валюты через кнопки"""
    query = update.callback_query
    await query.answer()
    
    bot = context.bot_data.get('currency_bot')
    user = query.from_user
    
    if query.data == "SET_MANUAL":
        await query.edit_message_text(
            "✏️ <b>Введите код валюты вручную:</b>\n\n"
            "Например: <code>EUR</code>, <code>JPY</code>, <code>BTC</code>\n"
            "Используйте международный код валюты (3 буквы).",
            parse_mode='HTML'
        )
        return SET_BASE_CURRENCY
    
    # Получаем код валюты из callback_data
    currency_code = query.data.replace("SET_", "")
    
    # Сохраняем настройку
    bot.set_user_setting(user.id, "base_currency", currency_code)
    
    # Получаем название валюты
    all_currencies = await bot.get_all_currencies()
    currency_name = all_currencies.get(currency_code, currency_code)
    
    await query.edit_message_text(
        f"✅ <b>Базовая валюта изменена!</b>\n\n"
        f"🎯 Теперь все курсы по умолчанию будут показываться в:\n"
        f"<b>{currency_name} ({currency_code})</b>\n\n"
        f"Пример: <code>/rate USD</code> покажет курс доллара к {currency_code}",
        parse_mode='HTML'
    )
    
    return ConversationHandler.END

async def set_base_currency_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ручного ввода базовой валюты"""
    bot = context.bot_data.get('currency_bot')
    user = update.effective_user
    currency_code = update.message.text.upper().strip()
    
    # Проверяем, существует ли такая валюта
    all_currencies = await bot.get_all_currencies()
    
    if currency_code not in all_currencies:
        # Проверяем через API
        rate = await bot.get_exchange_rate(currency_code, "USD")
        if rate is None:
            await update.message.reply_text(
                f"❌ <b>Валюта '{currency_code}' не найдена!</b>\n\n"
                f"Проверьте правильность кода валюты.\n"
                f"Используйте /list чтобы увидеть список доступных валют.\n"
                f"Попробуйте еще раз:",
                parse_mode='HTML'
            )
            return SET_BASE_CURRENCY
    
    # Сохраняем настройку
    bot.set_user_setting(user.id, "base_currency", currency_code)
    
    currency_name = all_currencies.get(currency_code, currency_code)
    
    await update.message.reply_text(
        f"✅ <b>Базовая валюта изменена!</b>\n\n"
        f"🎯 Теперь все курсы по умолчанию будут показываться в:\n"
        f"<b>{currency_name} ({currency_code})</b>\n\n"
        f"Пример: <code>/rate USD</code> покажет курс доллара к {currency_code}",
        parse_mode='HTML'
    )
    
    return ConversationHandler.END

async def set_amount_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало процесса установки суммы по умолчанию"""
    await update.message.reply_text(
        "💰 <b>Установите сумму по умолчанию:</b>\n\n"
        "Введите число (например: 100, 1000, 1.5)\n"
        "Эта сумма будет использоваться при конвертации.\n\n"
        "Пример: если установить 100, то команда <code>/rate EUR</code>\n"
        "покажет не только курс, но и стоимость 100 единиц валюты.",
        parse_mode='HTML'
    )
    
    return SET_AMOUNT

async def set_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Установка суммы по умолчанию"""
    bot = context.bot_data.get('currency_bot')
    user = update.effective_user
    
    try:
        amount = float(update.message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
        
        bot.set_user_setting(user.id, "default_amount", amount)
        
        await update.message.reply_text(
            f"✅ <b>Сумма по умолчанию установлена:</b> {amount:.2f}\n\n"
            f"Теперь команды будут показывать стоимость {amount:.2f} единиц валюты.",
            parse_mode='HTML'
        )
        
        return ConversationHandler.END
        
    except (ValueError, TypeError):
        await update.message.reply_text(
            "❌ <b>Неверный формат суммы!</b>\n\n"
            "Пожалуйста, введите положительное число.\n"
            "Например: 100, 1000, 1.5\n\n"
            "Попробуйте еще раз:",
            parse_mode='HTML'
        )
        return SET_AMOUNT

async def my_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать текущие настройки пользователя"""
    bot = context.bot_data.get('currency_bot')
    user = update.effective_user
    
    if not bot:
        bot = CurrencyBot()
        context.bot_data['currency_bot'] = bot
    
    base_currency = bot.get_user_setting(user.id, "base_currency", "RUB")
    default_amount = bot.get_user_setting(user.id, "default_amount", 1.0)
    
    # Получаем название базовой валюты
    all_currencies = await bot.get_all_currencies()
    base_name = all_currencies.get(base_currency, base_currency)
    
    config_text = (
        f"⚙️ <b>Ваши настройки:</b>\n\n"
        f"👤 <b>Пользователь:</b> {user.first_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        f"🎯 <b>Базовая валюта:</b>\n"
        f"{base_name} (<code>{base_currency}</code>)\n\n"
        f"💰 <b>Сумма по умолчанию:</b> {default_amount:.2f}\n\n"
        f"⚡ <b>Команды для изменения:</b>\n"
        f"/setbase - изменить базовую валюту\n"
        f"/setamount - изменить сумму по умолчанию"
    )
    
    await update.message.reply_text(config_text, parse_mode='HTML')

async def get_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /rate"""
    if not context.args:
        bot = context.bot_data.get('currency_bot')
        user = update.effective_user
        
        if bot:
            base_currency = bot.get_user_setting(user.id, "base_currency", "RUB")
        else:
            base_currency = "RUB"
        
        await update.message.reply_text(
            f"❌ <b>Использование:</b>\n\n"
            f"<code>/rate [ВАЛЮТА]</code> - курс к {base_currency}\n"
            f"<code>/rate [ИЗ] [В]</code> - конвертация\n"
            f"<code>/rate [СУММА] [ИЗ] [В]</code> - конвертация суммы\n\n"
            f"<b>Примеры:</b>\n"
            f"<code>/rate EUR</code> - курс Евро\n"
            f"<code>/rate BTC {base_currency}</code> - курс Bitcoin\n"
            f"<code>/rate 100 USD EUR</code> - 100 долларов в евро\n\n"
            f"⚙️ <b>Ваша базовая валюта:</b> {base_currency}\n"
            f"Изменить: /setbase",
            parse_mode='HTML'
        )
        return
    
    bot = context.bot_data.get('currency_bot')
    user = update.effective_user
    
    if not bot:
        bot = CurrencyBot()
        context.bot_data['currency_bot'] = bot
    
    # Получаем настройки пользователя
    base_currency = bot.get_user_setting(user.id, "base_currency", "RUB")
    default_amount = bot.get_user_setting(user.id, "default_amount", 1.0)
    
    args = context.args
    amount = default_amount
    
    # Определяем формат команды
    try:
        # Формат: /rate 100 USD EUR
        if len(args) == 3:
            amount = float(args[0])
            from_currency = args[1]
            to_currency = args[2]
        # Формат: /rate USD EUR
        elif len(args) == 2:
            from_currency = args[0]
            to_currency = args[1]
        # Формат: /rate EUR
        else:
            from_currency = args[0]
            to_currency = base_currency  # Используем базовую валюту пользователя
    except ValueError:
        from_currency = args[0]
        to_currency = base_currency if len(args) == 1 else args[1]
    
    # Получаем курс
    await update.message.reply_chat_action('typing')
    rate = await bot.get_exchange_rate(from_currency, to_currency)
    
    if rate is None:
        await update.message.reply_text(
            f"❌ Не удалось получить курс для <b>{from_currency}</b>.\n\n"
            f"Возможные причины:\n"
            f"• Неправильный код валюты\n"
            f"• Проблемы с API\n"
            f"• Валюта не поддерживается\n\n"
            f"Попробуйте:\n"
            f"1. Проверить код валюты: /search {from_currency}\n"
            f"2. Использовать другую пару валют\n"
            f"3. Попробовать позже",
            parse_mode='HTML'
        )
        return
    
    # Получаем названия валют
    all_currencies = await bot.get_all_currencies()
    from_name = all_currencies.get(from_currency.upper(), from_currency)
    to_name = all_currencies.get(to_currency.upper(), to_currency)
    
    # Рассчитываем результат
    result = amount * rate
    
    # Форматируем вывод
    response = (
        f"💱 <b>КУРС ВАЛЮТ</b>\n\n"
        f"📊 <b>{from_name} ({from_currency}) → {to_name} ({to_currency})</b>\n"
        f"┌{'─' * 31}┐\n"
        f"│ 1 {from_currency:<6} = {rate:>12.6f} {to_currency:<6} │\n"
        f"└{'─' * 31}┘\n"
    )
    
    if amount != 1.0:
        response += (
            f"\n🧮 <b>КОНВЕРТАЦИЯ:</b>\n"
            f"{amount:,.2f} {from_currency} = {result:,.2f} {to_currency}\n"
        )
    
    response += (
        f"\n⚙️ <b>Ваши настройки:</b>\n"
        f"• Базовая валюта: {base_currency}\n"
        f"• Сумма по умолчанию: {default_amount:.2f}\n\n"
        f"🕒 <i>Курс актуален на {datetime.now().strftime('%d.%m.%Y %H:%M')}</i>\n"
        f"<i>Изменить настройки: /setbase /setamount</i>"
    )
    
    # Добавляем кнопки для быстрого изменения
    if to_currency == base_currency:
        keyboard = [
            [
                InlineKeyboardButton("🔄 Сменить баз. валюту", callback_data=f"CHANGE_BASE_{from_currency}"),
                InlineKeyboardButton("💰 Изменить сумму", callback_data=f"CHANGE_AMOUNT_{from_currency}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(response, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await update.message.reply_text(response, parse_mode='HTML')

async def quick_change_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик быстрых изменений через кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    bot = context.bot_data.get('currency_bot')
    user = query.from_user
    
    if data.startswith("CHANGE_BASE_"):
        currency = data.replace("CHANGE_BASE_", "")
        bot.set_user_setting(user.id, "base_currency", currency)
        
        all_currencies = await bot.get_all_currencies()
        currency_name = all_currencies.get(currency, currency)
        
        await query.edit_message_text(
            f"✅ <b>Базовая валюта изменена!</b>\n\n"
            f"🎯 Теперь все курсы по умолчанию будут показываться в:\n"
            f"<b>{currency_name} ({currency})</b>\n\n"
            f"Используйте <code>/rate USD</code> чтобы увидеть курс доллара к {currency}",
            parse_mode='HTML'
        )
    
    elif data.startswith("CHANGE_AMOUNT_"):
        currency = data.replace("CHANGE_AMOUNT_", "")
        
        # Сохраняем текущую валюту в контексте для следующего шага
        context.user_data['change_amount_currency'] = currency
        
        await query.edit_message_text(
            f"💰 <b>Установите сумму для {currency}:</b>\n\n"
            f"Введите число (например: 100, 1000, 1.5)\n"
            f"Эта сумма будет использоваться по умолчанию для всех валют.",
            parse_mode='HTML'
        )
        
        return SET_AMOUNT

async def search_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /search"""
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Использование:</b>\n"
            "<code>/search [НАЗВАНИЕ ИЛИ КОД]</code>\n\n"
            "<b>Примеры:</b>\n"
            "<code>/search рубль</code>\n"
            "<code>/search BTC</code>\n"
            "<code>/search dollar</code>\n"
            "<code>/search золото</code>",
            parse_mode='HTML'
        )
        return
    
    search_query = " ".join(context.args)
    bot = context.bot_data.get('currency_bot')
    user = update.effective_user
    
    if not bot:
        bot = CurrencyBot()
        context.bot_data['currency_bot'] = bot
    
    base_currency = bot.get_user_setting(user.id, "base_currency", "RUB")
    
    await update.message.reply_chat_action('typing')
    results = await bot.search_currency(search_query)
    
    if not results:
        await update.message.reply_text(
            f"❌ Не найдено валют по запросу: <b>{search_query}</b>\n"
            f"Попробуйте другой запрос или используйте /list",
            parse_mode='HTML'
        )
        return
    
    response = f"🔍 <b>Результаты поиска '{search_query}':</b>\n\n"
    
    for i, (code, name) in enumerate(list(results.items())[:15], 1):  # Ограничим 15 результатами
        response += f"{i}. {name} (<code>{code}</code>)\n"
    
    if len(results) > 15:
        response += f"\n... и еще {len(results) - 15} валют\n"
    
    response += f"\n📊 <i>Найдено: {len(results)} валют</i>\n"
    response += f"<i>Используйте /rate {list(results.keys())[0]} чтобы увидеть курс к {base_currency}</i>"
    
    await update.message.reply_text(response, parse_mode='HTML')

async def list_currencies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /list"""
    bot = context.bot_data.get('currency_bot')
    user = update.effective_user
    
    if not bot:
        bot = CurrencyBot()
        context.bot_data['currency_bot'] = bot
    
    base_currency = bot.get_user_setting(user.id, "base_currency", "RUB")
    all_currencies = await bot.get_all_currencies()
    
    # Проверяем, хочет ли пользователь полный список
    show_all = context.args and context.args[0].lower() == "all"
    
    if show_all:
        # Показываем все валюты с пагинацией
        currencies_list = list(all_currencies.items())
        total_pages = (len(currencies_list) + 49) // 50  # 50 валют на страницу
        
        page = 1
        if len(context.args) > 1:
            try:
                page = int(context.args[1])
                page = max(1, min(page, total_pages))
            except ValueError:
                pass
        
        start_idx = (page - 1) * 50
        end_idx = min(start_idx + 50, len(currencies_list))
        
        response = f"📋 <b>Все валюты (страница {page}/{total_pages}):</b>\n\n"
        
        for i in range(start_idx, end_idx):
            code, name = currencies_list[i]
            response += f"• {name} (<code>{code}</code>)\n"
        
        response += f"\n📊 <i>Всего: {len(currencies_list)} валют</i>\n"
        
        # Добавляем навигацию
        keyboard = []
        if page > 1:
            keyboard.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"LIST_PAGE_{page-1}"))
        if page < total_pages:
            keyboard.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"LIST_PAGE_{page+1}"))
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup([keyboard])
            await update.message.reply_text(response, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(response, parse_mode='HTML')
        
    else:
        # Показываем только популярные валюты
        categories = {
            "💵 Основные валюты": ["RUB", "USD", "EUR", "GBP", "CNY", "JPY"],
            "🌍 Европа": ["CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "UAH", "BYN"],
            "🌏 Азия": ["KRW", "INR", "SGD", "THB", "MYR", "IDR", "VND", "PHP", "AED", "SAR"],
            "🌎 Америка": ["CAD", "MXN", "BRL", "ARS", "CLP", "COP", "PEN"],
            "🌍 Африка и Ближний Восток": ["ZAR", "EGP", "NGN", "TRY", "KZT"],
            "💰 Криптовалюты": ["BTC", "ETH", "XRP", "LTC", "BCH"],
            "🥇 Драгоценные металлы": ["XAU", "XAG", "XPT", "XPD"]
        }
        
        response = f"📋 <b>Популярные валюты</b>\n\n"
        response += f"🎯 <b>Ваша базовая валюта:</b> {base_currency}\n\n"
        
        for category, currencies in categories.items():
            response += f"<b>{category}:</b>\n"
            for code in currencies:
                if code in all_currencies:
                    response += f"• {all_currencies[code]} (<code>{code}</code>)\n"
            response += "\n"
        
        response += (
            f"📊 <i>Показано: {sum(len(c) for c in categories.values())} валют</i>\n"
            f"<i>Для полного списка используйте /list all</i>\n"
            f"<i>Для поиска конкретной валюты: /search [запрос]</i>"
        )
        
        await update.message.reply_text(response, parse_mode='HTML')

async def list_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик пагинации списка валют"""
    query = update.callback_query
    await query.answer()
    
    page = int(query.data.replace("LIST_PAGE_", ""))
    
    # Обновляем сообщение с новой страницей
    context.args = ["all", str(page)]
    await list_currencies(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога"""
    await update.message.reply_text(
        "❌ Операция отменена.",
        parse_mode='HTML'
    )
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке запроса.\n"
                "Пожалуйста, попробуйте еще раз или используйте /help для справки."
            )
        except:
            pass

async def post_init(application: Application) -> None:
    """Инициализация после запуска бота"""
    bot = CurrencyBot()
    application.bot_data['currency_bot'] = bot
    await bot.init_session()

async def post_shutdown(application: Application) -> None:
    """Завершение работы бота"""
    bot = application.bot_data.get('currency_bot')
    if bot:
        await bot.close_session()

def main() -> None:
    """Основная функция запуска бота"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    
    # Создаем ConversationHandler для настройки базовой валюты
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("setbase", set_base_currency_start),
            CommandHandler("setamount", set_amount_start),
            CallbackQueryHandler(quick_change_handler, pattern="^CHANGE_AMOUNT_")
        ],
        states={
            SET_BASE_CURRENCY: [
                CallbackQueryHandler(set_base_currency_button, pattern="^SET_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_base_currency_manual)
            ],
            SET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_amount)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rate", get_rate))
    application.add_handler(CommandHandler("search", search_currency))
    application.add_handler(CommandHandler("list", list_currencies))
    application.add_handler(CommandHandler("myconfig", my_config))
    
    # Регистрируем ConversationHandler
    application.add_handler(conv_handler)
    
    # Регистрируем обработчики кнопок
    application.add_handler(CallbackQueryHandler(list_page_handler, pattern="^LIST_PAGE_"))
    application.add_handler(CallbackQueryHandler(quick_change_handler, pattern="^CHANGE_BASE_"))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("🚀 Бот запускается...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
