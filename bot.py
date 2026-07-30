def parse_pearl_abyss(sent_ids):
    """
    Парсинг ТОЛЬКО крупных содержательных патчей с официального сайта Pearl Abyss.
    Используется комбинированный фильтр для отсеивания мелких новостей.
    """
    url = "https://blackdesert.pearlabyss.com/GlobalLab/en-US/News/Notice?_categoryNo=2"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    new_items = []
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"[Pearl Abyss] Ошибка загрузки страницы: {res.status_code}")
            return new_items
            
        soup = BeautifulSoup(res.text, "lxml")
        
        # Находим все ссылки на детальные страницы новостей
        all_links = soup.find_all("a", href=True)
        
        for a_tag in all_links:
            href = a_tag.get("href", "")
            if "Detail?" not in href:
                continue
            
            # Получаем ID новости
            board_no = href.split("_boardNo=")[-1].split("&")[0]
            
            # 🔥 КРИТЕРИЙ 1: Фильтр по ID (крупные патчи обычно имеют ID >= 19000)
            try:
                board_id = int(board_no)
                if board_id < 19000:
                    print(f"[Pearl Abyss] ⏭️ Пропущен патч (ID {board_id} < 19000)")
                    continue
            except ValueError:
                print(f"[Pearl Abyss] ⚠️ Не удалось распарсить ID: {board_no}")
                continue
            
            # Формируем полную ссылку
            if not href.startswith("http"):
                link = "https://blackdesert.pearlabyss.com" + href
            else:
                link = href
            
            # Находим заголовок новости
            title_tag = a_tag.find("span", class_="title") or a_tag.find("p", class_="title")
            if title_tag:
                title = title_tag.text.strip()
            else:
                title = a_tag.text.strip()
            
            title = " ".join(title.split())
            
            if not title:
                continue
            
            # 🔥 КРИТЕРИЙ 2: В названии должно быть слово "업데이트" (обновление)
            if "업데이트" not in title:
                print(f"[Pearl Abyss] ⏭️ Пропущено (нет '업데이트'): {title[:30]}...")
                continue
            
            # 🔥 КРИТЕРИЙ 3: Исключаем новости о безопасности и мелкие объявления
            exclude_keywords = ["보안", "모듈", "안내", "수정"]
            if any(kw in title for kw in exclude_keywords):
                print(f"[Pearl Abyss] ⏭️ Пропущено (содержит исключающее слово): {title[:30]}...")
                continue
            
            # Если новость прошла все фильтры - добавляем
            if link not in sent_ids:
                new_items.append({
                    "title": title,
                    "link": link,
                    "guid": link,
                    "desc": f"🇰🇷 Крупное обновление Global Lab (ID: {board_id})"
                })
                print(f"[Pearl Abyss] ✅ НОВЫЙ КРУПНЫЙ ПАТЧ: {title} (ID: {board_id})")
                
    except Exception as e:
        print(f"[Pearl Abyss] Ошибка парсинга: {e}")
    
    # Удаляем дубликаты и возвращаем в правильном порядке
    seen = set()
    unique_items = []
    for item in new_items[::-1]:
        if item["guid"] not in seen:
            seen.add(item["guid"])
            unique_items.append(item)
            
    return unique_items
