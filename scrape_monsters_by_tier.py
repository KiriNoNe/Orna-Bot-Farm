# scrape_monsters_by_tier.py
import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://playorna.com"
MONSTERS_URL = f"{BASE_URL}/codex/monsters/"
SAVE_DIR = "orna_monsters_sprites"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}


def download_image(img_url, filename):
    try:
        r = requests.get(img_url, headers=HEADERS, timeout=15, stream=True)
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    ✗ Ошибка: {e}")
        return False


def parse_page(soup, seen_urls):
    """Парсит одну страницу, возвращает (кол-во скачанных, список карточек)."""
    cards = soup.find_all("a", class_="codex-result-card")
    if not cards:
        return 0

    downloaded = 0
    for card in cards:
        name_tag = card.find("strong")
        name = name_tag.get_text(strip=True) if name_tag else "unknown"

        img_tag = card.find("img")
        if not img_tag or not img_tag.get("src"):
            continue

        img_url = urljoin(BASE_URL, img_tag["src"])

        if img_url in seen_urls:
            continue
        seen_urls.add(img_url)

        safe_name = name.lower().replace(" ", "_").replace("/", "_")
        filename = f"{safe_name}_{os.path.basename(img_url)}"
        filepath = os.path.join(SAVE_DIR, filename)

        if download_image(img_url, filepath):
            downloaded += 1
            print(f"    ✓ {name}")

    return downloaded


def main():
    os.makedirs(SAVE_DIR, exist_ok=True)

    TIER = int(input("Введите тир противников = "))   # <-- укажите тир

    seen_urls = set()
    total = 0
    page = 1

    while True:
        if page == 1:
            url = f"{MONSTERS_URL}?t={TIER}"
        else:
            url = f"{MONSTERS_URL}?t={TIER}&p={page}"

        print(f"\n=== Тир {TIER}, страница {page}: {url} ===")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ✗ Ошибка загрузки: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("a", class_="codex-result-card")
        print(f"  Карточек: {len(cards)}")

        if not cards:
            print("  Пусто — завершаем.")
            break

        downloaded = parse_page(soup, seen_urls)
        total += downloaded
        page += 1
        time.sleep(1)

    print(f"\n=== Готово! Скачано {total} спрайтов тира {TIER} ===")
    print(f"Папка: {os.path.abspath(SAVE_DIR)}")


if __name__ == "__main__":
    main()