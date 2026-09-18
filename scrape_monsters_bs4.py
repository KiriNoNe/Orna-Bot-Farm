# scrape_monsters_bs4.py
import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://playorna.com"
MONSTERS_URL = f"{BASE_URL}/codex/monsters/"
SAVE_DIR = "orna_monsters_sprites"
TOTAL_PAGES = 13

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}

def download_image(img_url, filename):
    """Скачивает изображение и сохраняет его."""
    try:
        r = requests.get(img_url, headers=HEADERS, timeout=15, stream=True)
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    ✗ Ошибка скачивания {img_url}: {e}")
        return False

def main():
    os.makedirs(SAVE_DIR, exist_ok=True)
    print(f"Папка для сохранения: {SAVE_DIR}\n")

    total_downloaded = 0
    seen_urls = set()  # чтобы не скачивать дубликаты

    for page in range(1, TOTAL_PAGES + 1):
        url = f"{MONSTERS_URL}?p={page}"
        print(f"=== Страница {page}/{TOTAL_PAGES}: {url} ===")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ✗ Не удалось загрузить страницу: {e}\n")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Ищем все карточки монстров
        cards = soup.find_all("a", class_="codex-result-card")
        print(f"  Найдено карточек: {len(cards)}")

        for card in cards:
            # Берём имя монстра из <strong>
            name_tag = card.find("strong")
            name = name_tag.get_text(strip=True) if name_tag else "unknown"

            # Берём URL картинки
            img_tag = card.find("img")
            if not img_tag or not img_tag.get("src"):
                continue

            img_url = urljoin(BASE_URL, img_tag["src"])

            # Пропускаем дубликаты
            if img_url in seen_urls:
                continue
            seen_urls.add(img_url)

            # Формируем имя файла: имя монстра + хвост URL
            # Например: "Apprentice of Earthen Might" → apprentice_of_earthen_might_acolyte_earth.png
            safe_name = name.lower().replace(" ", "_").replace("/", "_")
            url_tail = os.path.basename(img_url)
            filename = f"{safe_name}_{url_tail}"

            filepath = os.path.join(SAVE_DIR, filename)

            if download_image(img_url, filepath):
                total_downloaded += 1
                print(f"    ✓ {name} → {filename}")

        time.sleep(1)  # вежливая пауза между страницами

    print(f"\n=== Готово! Скачано {total_downloaded} спрайтов ===")
    print(f"Файлы лежат в: {os.path.abspath(SAVE_DIR)}")

if __name__ == "__main__":
    main()