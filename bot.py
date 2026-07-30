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
    """Парсинг сайта Orbit Games с полным набором заголовков и обходом Cloudflare"""
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
    
    try:
        # Передаем заголовки вместе с эмуляцией отпечатка Chrome 120/122
        res = cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=30)
        
        if res.status_code != 200:
            print(f"[Orbit] Сайт вернул код ошибки: {res.status_code}")
            return new_items
            
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
                    "desc": "🇰🇷 Перевод от \"Орбита игр\""
                })
    except Exception as e:
        print(f"[Orbit] Запрос заблокирован или недоступен: {e}")
        
    return new_items[::-1]

def parse_pearl_abyss(sent_ids):
    """Парсинг официального сайта Pearl Abyss Global Lab Notice"""
    url = "https://blackdesert.pearlabyss.com/GlobalLab/en-US/News/Notice?_categoryNo=2"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    new_items = []
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"[Pearl Abyss] Ошибка загрузки страницы: {res.status_code}")
            return new_items
            
        soup = BeautifulSoup(res.text, "lxml")
        list_container = soup.find("div", class_="board_list_block") or soup.find("ul", class_="news_list")
        if not list_container:
            links = soup.find_all("a", href=True)
        else:
            links = list_container.find_all("a", href=True)
            
        for a_tag in links:
            if "Detail?" in a_tag["href"]:
                link = a_tag["href"]
                if not link.startswith("http"):
                    link = "https://blackdesert.pearlabyss.com" + link
                
                title_tag = a_tag.find("span", class_="title") or a_tag.find("p", class_="title")
                title = title_tag.text.strip() if title_tag else a_tag.text.strip()
                
                title = " ".join(title.split())
                if not title:
                    continue
                
                if not title.startswith("[Updates]"):
                    title = f"[Updates] {title}"
                
                if link not in sent_ids:
                    new_items.append({
                        "title": title,
                        "link": link,
                        "guid": link,
                        "desc": "🇰🇷 Вышло обновление (Global Lab)"
                    })
    except Exception as e:
        print(f"[Pearl Abyss] Ошибка парсинга: {e}")
        
    seen = set()
    unique_items = []
    for item in new_items[::-1]:
        if item["guid"] not in seen:
            seen.add(item["guid"])
            unique_items.append(item)
            
    return unique_items

def send_to_discord(item):
    """Финальный чистый вариант сообщения без ломающегося Markdown"""
    payload = {
        "embeds": [
            {
                "color": 16618511,  # Фирменная оранжевая полоска слева
                "description": f"🇰🇷 Вышло обновление (Global Lab)\n\n**[{item['title']}]({item['link']})**",
                "image": {
                    "url": "https://cdn.discordapp.com/attachments/1108501100203622470/1532353905969598554/image.png"
                }
            }
        ]
    }
    
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code == 429:
            retry_after = res.json().get("retry_after", 5)
            print(f"Рейт-лимит Discord. Ожидание {retry_after} сек...")
            time.sleep(retry_after)
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
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
