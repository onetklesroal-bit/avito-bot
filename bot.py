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
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Application

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
        print(f"Ошибка веб-сервера: {e}")

threading.Thread(target=run_web_server, daemon=True).start()

# Функция самопинга от засыпания на Render
def self_ping():
    app_url = os.environ.get("RENDER_EXTERNAL_URL", "https://avito-bot-aqj8.onrender.com")
    while True:
        time.sleep(300)  # каждые 5 минут
        try:
            requests.get(app_url, timeout=10)
            print("[PUMP] Самопинг выполнен.")
        except Exception:
            pass

threading.Thread(target=self_ping, daemon=True).start()

# Настройки
TELEGRAM_BOT_TOKEN = "8630475376:AAGNBBc4PfpYSOnOMApxce_uWUpFt0J3_Gs"
MY_CHAT_ID = 6059893988
GEMINI_API_KEY = "AQ.Ab8RN6LssNxjN6kuojyR82YAinI0olE30S3mu8G1XknZNzFdKQ"

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

is_searching = False
bot_application: Application = None

# Пул браузеров для защиты от бана
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def check_ad_with_ai(title, description, price):
    prompt = f"""
    Ты профессиональный перекуп и эксперт по смартфонам. Проанализируй объявление с Авито:
    - Заголовок: {title}
    - Цена: {price} руб.
    - Описание: {description}
    
    Жесткие критерии отбора:
    1. Уровень: Это НЕ ультрабюджетка (никаких слабых старых дешманок вроде старых Redmi A-серий). Интересны только нормальные среднебюджетники и флагманы (Xiaomi, Poco, Samsung, Realme, iPhone, OnePlus, Vivo, iQOO, Pixel, Honor и т.д.).
    2. Возраст: Модель должна быть примерно от 2020 года выпуска и новее.
    3. Состояние: Это не убитый в хлам хлам, не заблокированный кирпич и не мусор за три копейки, который никому не нужен.
    4. Цена: Цена должна быть выгодной (ниже рынка / под перепродажу или личное использование).
    
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
    # Общая ссылка на все мобильные телефоны в Краснодаре без привязки к конкретной модели
    search_url = "https://www.avito.ru/krasnodar/telefony/mobilnye_telefony-ASgBAgICA0Sztg4"

    while True:
        delay = random.randint(70, 130)
        time.sleep(delay)

        if not is_searching or not bot_application:
            continue

        print("[INFO] Сканирую общую ленту Авито...")
        try:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept-Language": "ru-RU,ru;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
            
            response = requests.get(search_url, headers=headers, timeout=12)
            if response.status_code != 200:
                print(f"[WARN] Авито ответил кодом {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.find_all('div', {'data-marker': 'item'})[:5]  # Берем первые 5 свежих объявлений
            
            for item in items:
                title_elem = item.find('h3', {'itemprop': 'name'})
                price_elem = item.find('meta', {'itemprop': 'price'})
                
                if title_elem and price_elem:
                    title = title_elem.text.strip()
                    price = price_elem.get('content', '0')
                    
                    ai_verdict = check_ad_with_ai(title, "Описание не получено напрямую", price)
                    
                    if "ПОДХОДИТ" in ai_verdict:
                        msg = f"🔥 **Найден ликвидный вариант!**\n\n📌 **{title}**\n💰 **Цена:** {price} руб.\n\n🤖 **Вердикт ИИ:**\n{ai_verdict}"
                        asyncio.run(bot_application.bot.send_message(chat_id=MY_CHAT_ID, text=msg, parse_mode="Markdown"))
        except Exception as e:
            print(f"[ERROR] Ошибка сканера: {e}")

threading.Thread(target=background_scanner, daemon=True).start()

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_searching
    if update.effective_user.id != MY_CHAT_ID:
        return
    is_searching = True
    await update.message.reply_text("🟢 Всеобщий поиск смартфонов и ИИ-фильтр **ВКЛЮЧЕНЫ** 24/7!", parse_mode="Markdown")

async def stop_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_searching
    if update.effective_user.id != MY_CHAT_ID:
        return
    is_searching = False
    await update.message.reply_text("🔴 Поиск Авито **ВЫКЛЮЧЕН**.", parse_mode="Markdown")

async def status_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_searching
    if update.effective_user.id != MY_CHAT_ID:
        return
    status = "АКТИВЕН 🟢 (Ищет все бренды, защищен)" if is_searching else "ОСТАНОВЛЕН 🔴"
    await update.message.reply_text(f"Статус бота: {status}")

def main():
    global bot_application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    bot_application = app

    app.add_handler(CommandHandler("start", start_search))
    app.add_handler(CommandHandler("stop", stop_search))
    app.add_handler(CommandHandler("status", status_check))

    print("Всеядный облачный снайпер Авито запущен...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
      
