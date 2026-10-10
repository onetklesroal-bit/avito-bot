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
        time.sleep(300)  # каждые 5 минут
        try:
            requests.get(app_url, timeout=10)
            print("[PUMP] Самопинг выполнен, бот бодрствует.")
        except Exception:
            pass

threading.Thread(target=self_ping, daemon=True).start()

# Настройки
TELEGRAM_BOT_TOKEN = "8630475376:AAGNBBc4PfpYSOnOMApxce_uWUpFt0J3_Gs"
MY_CHAT_ID = 6059893988
GEMINI_API_KEY = "AQ.Ab8RN6LssNxjN6kuojyR82YAinI0olE30S3mu8G1XknZNzFdKQ"

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

# Состояния бота
is_searching = False
current_brand = "all"  # По умолчанию ищем все бренды
waiting_for_brand = False
bot_application: Application = None

# Пул браузеров для защиты от бана
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def get_search_url():
    """Формирует ссылку на Авито в зависимости от выбранного бренда"""
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
    1. ОТСЕКАЙ (НЕ ПОДХОДИТ): явный мусор, кнопочные телефоны, старые слабые бюджетки до 2020 года (всякие старые слабые Redmi/Samsung J-серии), заблокированные аппараты ("кирпичи", под iCloud/Google аккаунт), или очевидно убитые в хлам трубки (если в заголовке прямо написано "на запчасти", "разбит вдребезги").
    2. ПРОПУСКАЙ (ПОДХОДИТ): любые нормальные среднебюджетники и флагманы (Xiaomi, Poco, Samsung, iPhone, Realme, OnePlus, Pixel, Vivo, Honor и т.д.), если цена выглядит ниже рынка или адекватной под перепродажу/восстановление. 
    *Важно:* Если сомневаешься — лучше перестрахуйся и скажи ПОДХОДИТ, чтобы пользователь сам оценил объявление.
    
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

    while True:
        delay = random.randint(200, 350)
        print(f"[SLEEP] Жду {delay} секунд перед следующим сканированием...")
        time.sleep(delay)

        if not is_searching or not bot_application:
            print("[INFO] Поиск выключен или бот не инициализирован, пропускаю цикл.")
            continue

        search_url = get_search_url()
        print(f"[INFO] Начинаю сканирование Авито. Ссылка: {search_url}")
        
        try:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept-Language": "ru-RU,ru;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
            
            response = requests.get(search_url, headers=headers, timeout=12)
            print(f"[DEBUG] Статус ответа Авито: {response.status_code}")
            
            if response.status_code != 200:
                print(f"[WARN] Авито ответил кодом {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.find_all('div', {'data-marker': 'item'})[:5]
            print(f"[DEBUG] Найдено свежих объявлений на странице: {len(items)}")
            
            for item in items:
                title_elem = item.find('h3', {'itemprop': 'name'})
                price_elem = item.find('meta', {'itemprop': 'price'})
                link_elem = item.find('a', {'data-marker': 'item-title'})
                
                if title_elem and price_elem:
                    title = title_elem.text.strip()
                    price = price_elem.get('content', '0')
                    link = "https://www.avito.ru" + link_elem['href'] if link_elem and 'href' in link_elem.attrs else search_url
                    
                    print(f"[SCAN] Проверяю объявление: '{title}' | Цена: {price} руб.")
                    
                    ai_verdict = check_ad_with_ai(title, "Описание не получено напрямую", price)
                    
                    if "ПОДХОДИТ" in ai_verdict:
                        print(f"[MATCH] Найден подходящий вариант! Отправляю в Telegram...")
                        msg = f"🔥 **Найден ликвидный вариант!**\n\n📌 **{title}**\n💰 **Цена:** {price} руб.\n\n🔗 [Открыть объявление на Авито]({link})\n\n🤖 **Вердикт ИИ:**\n{ai_verdict}"
                        asyncio.run(bot_application.bot.send_message(chat_id=MY_CHAT_ID, text=msg, parse_mode="Markdown", disable_web_page_preview=False))
                    else:
                        print(f
