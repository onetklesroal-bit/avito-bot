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
                link_elem = item.find('a', {'data-marker': 'item-title'}) # Ссылка на объявление
                
                if title_elem and price_elem:
                    title = title_elem.text.strip()
                    price = price_elem.get('content', '0')
                    
                    # Достаем ссылку и превращаем ее в полный рабочий адрес Авито
                    link = "https://www.avito.ru" + link_elem['href'] if link_elem and 'href' in link_elem.attrs else search_url
                    
                    print(f"[SCAN] Проверяю объявление: '{title}' | Цена: {price} руб.")
                    
                    ai_verdict = check_ad_with_ai(title, "Описание не получено напрямую", price)
                    
                    if "ПОДХОДИТ" in ai_verdict:
                        print(f"[MATCH] Найден подходящий вариант! Отправляю в Telegram...")
                        # Добавили красивую кнопку-ссылку в сообщение
                        msg = f"🔥 **Найден ликвидный вариант!**\n\n📌 **{title}**\n💰 **Цена:** {price} руб.\n\n🔗 [Открыть объявление на Авито]({link})\n\n🤖 **Вердикт ИИ:**\n{ai_verdict}"
                        asyncio.run(bot_application.bot.send_message(chat_id=MY_CHAT_ID, text=msg, parse_mode="Markdown", disable_web_page_preview=False))
                    else:
                        print(f"[SKIP] Отсечено ИИ (не подошло).")
                        
        except Exception as e:
            print(f"[ERROR] Ошибка в фоновом сканере: {e}")
          
