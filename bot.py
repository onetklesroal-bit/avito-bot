import os
import time
import random
import threading
import asyncio
import http.server
import socketserver
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, Application

# Порт для Render
PORT = int(os.environ.get("PORT", 10000))

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and self-pinging!")

def run_web_server():
    try:
        with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
            httpd.serve_forever()
    except Exception as e:
        print(f"[ERROR] Ошибка веб-сервера: {e}")

threading.Thread(target=run_web_server, daemon=True).start()

# Функция самопинга от засыпания на Render
def self_ping():
    app_url = os.environ.get("RENDER_EXTERNAL_URL", "https://avito-bot-aqj8.onrender.com")
    while True:
        time.sleep(300)
        try:
            requests.get(app_url, timeout=10)
            print("[PUMP] Самопинг выполнен, бот бодрствует.")
        except Exception:
            pass

threading.Thread(target=self_ping, daemon=True).start()

# Загрузка настроек
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MY_CHAT_ID = int(os.environ.get("MY_CHAT_ID", "6059893988"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

# Состояния бота
is_searching = False
current_brand = "all"
waiting_for_brand = False
bot_application: Application = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def get_search_url():
    base_url = "https://www.avito.ru/krasnodar/telefony/mobilnye_telefony-ASgBAgICA0Sztg4"
    if current_brand.lower() == "all":
        print("[CONFIG] Режим поиска: ВСЕ БРЕНДЫ")
        return base_url
    else:
        print(f"[CONFIG] Режим поиска по бренду: {current_brand}")
        return f"{base_url}?q={current_brand}"

def check_ad_with_ai(title, description, price):
    prompt = f"""
    Ты помощник опытного перекупа смартфонов. Твоя задача — отсекать явный хлам, но ВСЕГДА пропускать потенциально выгодные или интересные предложения.
    
    Данные объявления:
    - Заголовок: {title}
    - Цена: {price} руб.
    
    Правила отбора:
    1. ОТСЕКАЙ (НЕ ПОДХОДИТ): явный мусор, кнопочные телефоны, старые слабые бюджетки до 2020 года, заблокированные аппараты ("кирпичи", под iCloud/Google аккаунт), или очевидно убитые в хлам трубки.
    2. ПРОПУСКАЙ (ПОДХОДИТ): любые нормальные среднебюджетники и флагманы (Xiaomi, Poco, Samsung, iPhone, Realme, OnePlus, Pixel, Vivo, Honor и т.д.), если цена выглядит адекватной.
    
    Дай ответ строго в таком формате:
    ВЕРДИКТ: [ПОДХОДИТ / НЕ ПОДХОДИТ]
    ПРИЧИНА: кратко почему
    """
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Ошибка ИИ: {e}"

def background_scanner():
    global is_searching, bot_application
    print("[SCANNER] Фоновый поток сканера запущен и ждет команды включения...")

    while True:
        delay = random.randint(30, 50)  # Сделали пока задержку короче, чтобы быстрее проверить в логах
        time.sleep(delay)

        if not is_searching:
            print("[INFO] Поиск выключен (нажми /start в телеграме).")
            continue

        if not bot_application:
            print("[INFO] Бот еще не инициализирован в Telegram...")
            continue

        search_url = get_search_url()
        print(f"[INFO] Сканирую Авито по ссылке: {search_url}")
        
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            response = requests.get(search_url, headers=headers, timeout=12)
            print(f"[DEBUG] Статус ответа Авито: {response.status_code}")
            
            if response.status_code != 200:
                print(f"[WARN] Авито ответил кодом {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.find_all('div', {'data-marker': 'item'})[:3]
            print(f"[DEBUG] Найдено объявлений: {len(items)}")
            
            for item in items:
                title_elem = item.find('h3', {'itemprop': 'name'})
                price_elem = item.find('meta', {'itemprop': 'price'})
                link_elem = item.find('a', {'data-marker': 'item-title'})
                
                if title_elem and price_elem:
                    title = title_elem.text.strip()
                    price = price_elem.get('content', '0')
                    link = "https://www.avito.ru" + link_elem['href'] if link_elem and 'href' in link_elem.attrs else search_url
                    
                    print(f"[SCAN] Проверяю: '{title}' | Цена: {price}")
                    ai_verdict = check_ad_with_ai(title, "Описание не получено напрямую", price)
                    
                    if "ПОДХОДИТ" in ai_verdict:
                        print(f"[MATCH] Нашел подходящий! Отправляю...")
                        msg = f"🔥 **Найден ликвидный вариант!**\n\n📌 **{title}**\n💰 **Цена:** {price} руб.\n\n🔗 [Открыть на Авито]({link})\n\n🤖 {ai_verdict}"
                        asyncio.run(bot_application.bot.send_message(chat_id=MY_CHAT_ID, text=msg, parse_mode="Markdown"))
                    else:
                        print(f"[SKIP] Отсечено ИИ.")
        except Exception as e:
            print(f"[ERROR] Ошибка сканера: {e}")

threading.Thread(target=background_scanner, daemon=True).start()

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_searching
    if update.effective_user.id != MY_CHAT_ID:
        return
    is_searching = True
    await update.message.reply_text(f"🟢 Поиск ВКЛЮЧЕН! Бренд: **{current_brand}**", parse_mode="Markdown")

async def stop_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_searching
    if update.effective_user.id != MY_CHAT_ID:
        return
    is_searching = False
    await update.message.reply_text("🔴 Поиск ВЫКЛЮЧЕН.", parse_mode="Markdown")

async def status_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_searching
    status = "АКТИВЕН 🟢" if is_searching else "ОСТАНОВЛЕН 🔴"
    await update.message.reply_text(f"Статус: {status}\nБренд: **{current_brand}**", parse_mode="Markdown")

async def brend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_for_brand, current_brand
    if update.effective_user.id != MY_CHAT_ID:
        return
    if context.args:
        current_brand = context.args[0].strip()
        waiting_for_brand = False
        await update.message.reply_text(f"✅ Бренд изменен на: **{current_brand}**", parse_mode="Markdown")
    else:
        waiting_for_brand = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_for_brand, current_brand
    if update.effective_user.id != MY_CHAT_ID:
        return
    if waiting_for_brand:
        current_brand = update.message.text.strip()
        waiting_for_brand = False
        await update.message.reply_text(f"✅ Принято! Бренд: **{current_brand}**", parse_mode="Markdown")

def main():
    global bot_application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    bot_application = app

    app.add_handler(CommandHandler("start", start_search))
    app.add_handler(CommandHandler("stop", stop_search))
    app.add_handler(CommandHandler("status", status_check))
    app.add_handler(CommandHandler("brend", brend_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Бот успешно запущен и слушает Telegram...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
