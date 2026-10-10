import os
import time
import threading
import http.server
import socketserver
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Application

# Запуск простого веб-сервера для Render, чтобы сервис не засыпал
PORT = int(os.environ.get("PORT", 10000))

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def run_web_server():
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# Конфигурация
TELEGRAM_BOT_TOKEN = "8630475376:AAGNBBc4PfpYSOnOMApxce_uWUpFt0J3_Gs"
MY_CHAT_ID = 6059893988
GEMINI_API_KEY = "AQ.Ab8RN6LssNxjN6kuojyR82YAinI0olE30S3mu8G1XknZNzFdKQ"

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

is_searching = False
bot_application: Application = None

def check_ad_with_ai(title, description, price):
    prompt = f"""
    Ты профессиональный эксперт по проверке объявлений о продаже смартфонов на Авито. 
    Проанализируй данные объявления:
    - Заголовок: {title}
    - Цена: {price} руб.
    - Описание: {description}
    
    Строго ответь по пунктам, является ли вариант выгодным и безопасным для покупки:
    1. Имя модели: совпадает ли реальная модель с заявленной в заголовке?
    2. Обмен: продают ли телефон за деньги, или это ТОЛЬКО обмен? (Если обмен, товар НЕ подходит).
    3. Резерв: указано ли, что товар зарезервирован?
    
    Дай четкий ответ в таком виде:
    ВЕРДИКТ: [ПОДХОДИТ / НЕ ПОДХОДИТ]
    ПРИЧИНА: кратко почему
    """
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Ошибка ИИ: {e}"

def background_scanner():
    """Фоновый цикл проверки Авито каждые 60 секунд"""
    global is_searching, bot_application
    search_url = "https://www.avito.ru/krasnodar/telefony/mobilnye_telefony-ASgBAgICA0Sztg4?q=pixel"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    while True:
        time.sleep(60)
        if not is_searching or not bot_application:
            continue

        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.find_all('div', {'data-marker': 'item'})[:3]
            
            for item in items:
                title_elem = item.find('h3', {'itemprop': 'name'})
                price_elem = item.find('meta', {'itemprop': 'price'})
                
                if title_elem and price_elem:
                    title = title_elem.text.strip()
                    price = price_elem.get('content', '0')
                    
                    ai_verdict = check_ad_with_ai(title, "Описание не получено напрямую", price)
                    
                    if "ПОДХОДИТ" in ai_verdict:
                        msg = f"🔥 **Выгодный вариант найден!**\n\n📌 **{title}**\n💰 **Цена:** {price} руб.\n\n🤖 **Вердикт ИИ:**\n{ai_verdict}"
                        # Синхронная отправка сообщения через бота
                        import asyncio
                        asyncio.run(bot_application.bot.send_message(chat_id=MY_CHAT_ID, text=msg, parse_mode="Markdown"))
        except Exception as e:
            print(f"Ошибка в фоновом сканере: {e}")

# Запускаем фоновый поток сканирования
threading.Thread(target=background_scanner, daemon=True).start()

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_searching
    if update.effective_user.id != MY_CHAT_ID:
        return
    is_searching = True
    await update.message.reply_text("🟢 Поиск Авито и ИИ-анализ **ВКЛЮЧЕНЫ** на сервере 24/7!", parse_mode="Markdown")

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
    status = "АКТИВЕН 🟢 (Работает в облаке)" if is_searching else "ОСТАНОВЛЕН 🔴"
    await update.message.reply_text(f"Статус бота: {status}")

def main():
    global bot_application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    bot_application = app

    app.add_handler(CommandHandler("start", start_search))
    app.add_handler(CommandHandler("stop", stop_search))
    app.add_handler(CommandHandler("status", status_check))

    print("Облачный снайпер Авито запущен...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
