import os
import json
import requests
from bs4 import BeautifulSoup
import time
from curl_cffi import requests as cffi_requests

DB_FILE = "sent_news.json"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")

def load_sent_ids():
    """Безопасная загрузка ID отправленных новостей с защитой от пустых файлов"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return set()
                return set(json.loads(content))
        except json.JSONDecodeError:
            print(f"Предупреждение: Файл {DB_FILE} поврежден или пуст. Создаем новую базу.")
            return set()
    return set()

def save_sent_ids(sent_ids):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_ids), f, ensure_ascii=False, indent=4)

def parse_orbit_games(sent_ids):
    """Парсинг сайта Orbit Games с флагом России и защитой от тайм-аутов"""
    url = "https://orbit-games.com/category/black-desert/global-lab/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }
    new_items = []
    
    for attempt in range(1, 4):
        try:
            res = cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=30)
            
            if res.status_code != 200:
                print(f"[Orbit] Сайт вернул код ошибки: {res.status_code} (попытка {attempt}/3)")
                time.sleep(3)
                continue
                
            soup = BeautifulSoup(res.text, "lxml")
            articles = soup.find_all("article")
            
            for article in articles:
                header_tag = article.find("h2") or article.find("h1")
                if not header_tag:
                    continue
                
                a_tag = header_tag.find("a")
                if not a_tag:
                    continue
                    
                title = a_tag.text.strip()
                link = a_tag["href"]
                
                if link not in sent_ids:
                    new_items.append({
                        "title": title,
                        "link": link,
                        "guid": link,
                        "desc": ":flag_ru: Перевод от \"Орбита игр\""
                    })
            break
            
        except Exception as e:
            print(f"[Orbit] Ошибка на попытке {attempt}/3: {e}")
            if attempt < 3:
                time.sleep(5)
            else:
                print("[Orbit] Не удалось получить ответ после 3 попыток, пропускаем.")
        
    return new_items[::-1]

def parse_pearl_abyss(sent_ids):
    """
    Парсинг ТОЛЬКО крупных патчей (ID >= 19000) с официального сайта Pearl Abyss.
    Мелкие новости и объявления о безопасности (ID 13000-13393) игнорируются.
    """
    url = "https://blackdesert.pearlabyss.com/GlobalLab/en-US/News/Notice?_categoryNo=2"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    new_items = []
    seen_links = set()  # Для отслеживания уже найденных ссылок
    
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
            
            # Получаем ID новости из URL
            board_no = href.split("_boardNo=")[-1].split("&")[0]
            
            try:
                board_id = int(board_no)
            except ValueError:
                print(f"[Pearl Abyss] ⚠️ Не удалось распарсить ID: {board_no}")
                continue
            
            # Фильтр: Только ID >= 19000 (крупные патчи)
            if board_id < 19000:
                if board_id >= 13000:
                    print(f"[Pearl Abyss] ⏭️ Пропущена мелкая новость (ID {board_id})")
                continue
            
            # Формируем полную ссылку
            if not href.startswith("http"):
                link = "https://blackdesert.pearlabyss.com" + href
            else:
                link = href
            
            # Проверяем, не обрабатывали ли уже эту ссылку
            if link in seen_links:
                continue
            seen_links.add(link)
            
            # Находим заголовок новости
            title_tag = a_tag.find("span", class_="title") or a_tag.find("p", class_="title")
            if title_tag:
                title = title_tag.text.strip()
            else:
                title = a_tag.text.strip()
            
            title = " ".join(title.split())
            
            if not title:
                continue
            
            # Если новость прошла фильтр по ID - добавляем
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
    
    # Удаляем дубликаты (на всякий случай)
    seen = set()
    unique_items = []
    for item in new_items[::-1]:
        if item["guid"] not in seen:
            seen.add(item["guid"])
            unique_items.append(item)
            
    return unique_items

def send_to_discord(item):
    """Отправка сообщения через Components V2 с контейнером и двумя разделителями"""
    webhook_url_v2 = f"{DISCORD_WEBHOOK_URL}?with_components=true"
    
    payload = {
        "flags": 32768,
        "components": [
            {
                "type": 17,
                "accent_color": 16618511,
                "spoiler": False,
                "components": [
                    {"type": 14},
                    {"type": 10, "content": str(item["desc"])},
                    {"type": 14},
                    {"type": 10, "content": f"**[{item['title']}]({item['link']})**"}
                ]
            }
        ]
    }
    
    try:
        res = requests.post(webhook_url_v2, json=payload, timeout=10)
        if res.status_code == 429:
            retry_after = res.json().get("retry_after", 5)
            print(f"Рейт-лимит Discord. Ожидание {retry_after} сек...")
            time.sleep(retry_after)
            requests.post(webhook_url_v2, json=payload, timeout=10)
        elif res.status_code not in [200, 204]:
            print(f"Ошибка Discord API: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Не удалось отправить в Discord: {e}")

def main():
    if not DISCORD_WEBHOOK_URL:
        print("Ошибка: Переменная DISCORD_WEBHOOK не найдена в секретах GitHub.")
        return

    sent_ids = load_sent_ids()
    all_new_stories = []

    print("Проверка Orbit Games...")
    all_new_stories.extend(parse_orbit_games(sent_ids))
    
    print("Проверка Pearl Abyss Global Lab...")
    all_new_stories.extend(parse_pearl_abyss(sent_ids))

    if all_new_stories:
        for story in all_new_stories:
            if story["guid"] not in sent_ids:
                print(f"Новое событие: {story['title']}")
                send_to_discord(story)
                sent_ids.add(story["guid"])
                time.sleep(2)
        
        save_sent_ids(sent_ids)
        print("База данных JSON успешно обновлена в репозитории.")
    else:
        print("Никаких новых патч-ноутов или переводов не найдено.")

if __name__ == "__main__":
    main()
