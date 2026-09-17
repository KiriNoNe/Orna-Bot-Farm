import cv2
import numpy as np
import os
import time
import glob
from adb_shell.adb_device import AdbDeviceTcp

# ---------- ADB ----------
ADB_HOST = '127.0.0.1'
ADB_PORT = 5555
DEVICE_SCREEN_PATH = '/sdcard/_bot_screen.png'
LOCAL_SCREEN_PATH = 'screenshots/_temp.png'

# ---------- Пути ----------
TEMPLATES_DIR = 'templates'
SCREENSHOTS_DIR = 'screenshots'

# ---------- Координаты ----------
START_BATTLE_BTN = (886, 313)
ATTACK_BTN       = (415, 817)

# ---------- Пороги ----------
MONSTER_THRESHOLD       = 0.75
BATTLE_ANCHOR_THRESHOLD = 0.75
CONTINUE_THRESHOLD      = 0.75

# ---------- Паузы (секунды) ----------
DELAY_AFTER_MONSTER_TAP  = 1.8
DELAY_AFTER_START_BATTLE = 3.5
DELAY_BETWEEN_ATTACKS    = 2.5
DELAY_AFTER_CONTINUE     = 2.0
DELAY_IF_NO_MONSTER      = 1.5
MAX_ATTACKS_PER_BATTLE   = 30
MAX_CONTINUE_WAIT        = 10      # попыток найти кнопку внутри одного раунда (по 0.5 сек)
MAX_CONTINUE_ROUNDS      = 5       # максимум экранов "Продолжить" подряд (победа, лвл-ап, лут...)


# ---------- ADB ----------
def connect():
    d = AdbDeviceTcp(ADB_HOST, ADB_PORT, default_transport_timeout_s=9.)
    d.connect()
    return d


def get_screenshot(device):
    device.shell(f'screencap -p {DEVICE_SCREEN_PATH}')
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    device.pull(DEVICE_SCREEN_PATH, LOCAL_SCREEN_PATH)
    return cv2.imread(LOCAL_SCREEN_PATH)


def tap(device, x, y):
    device.shell(f'input tap {x} {y}')


# ---------- Распознавание ----------
def load_templates(exclude=None):
    exclude = exclude or []
    templates = []
    for path in sorted(glob.glob(os.path.join(TEMPLATES_DIR, '*.png'))):
        name = os.path.basename(path)
        if name in exclude:
            continue
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is not None:
            templates.append((name, img))
            print(f"  Загружен: {name} {img.shape[1]}x{img.shape[0]}")
    return templates


def find_template(screen, template, threshold):
    if template.shape[0] > screen.shape[0] or template.shape[1] > screen.shape[1]:
        return None
    res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val >= threshold:
        h, w = template.shape[:2]
        return (max_loc[0] + w // 2, max_loc[1] + h // 2, max_val)
    return None


def find_monster(screen, templates, threshold=MONSTER_THRESHOLD):
    best = None
    for name, template in templates:
        r = find_template(screen, template, threshold)
        if r:
            x, y, conf = r
            if best is None or conf > best[0]:
                best = (conf, x, y, name)
    if best is None:
        return None
    conf, x, y, name = best
    return (x, y, name, conf)


def find_continue_and_click(device, continue_template):
    """
    Жмёт 'Продолжить', пока она появляется на экране.
    Обрабатывает случаи: экран победы, повышение уровня, экран лута и т.д.
    Возвращает True, если все экраны закрыты.
    """
    total_clicks = 0

    for round_num in range(MAX_CONTINUE_ROUNDS):
        found_in_round = False

        # Внутри одного раунда ждём появления кнопки до MAX_CONTINUE_WAIT * 0.5 секунд
        for attempt in range(MAX_CONTINUE_WAIT):
            screen = get_screenshot(device)
            if screen is None:
                time.sleep(0.5)
                continue

            result = find_template(screen, continue_template, CONTINUE_THRESHOLD)
            if result:
                x, y, conf = result
                total_clicks += 1
                print(f"  → 'Продолжить' #{total_clicks} ({x},{y}) conf={conf:.2f}, клик")
                tap(device, x, y)
                time.sleep(DELAY_AFTER_CONTINUE)
                found_in_round = True
                break

            time.sleep(0.5)

        if not found_in_round:
            # Кнопка не появилась в этом раунде
            if round_num == 0:
                print("  ⚠ Кнопка 'Продолжить' не появилась")
                return False
            else:
                print(f"  ✓ Все экраны закрыты. Всего кликов 'Продолжить': {total_clicks}")
                return True

    print(f"  ⚠ Достигнут лимит раундов ({MAX_CONTINUE_ROUNDS}). Возможно, зациклились.")
    return False


# ---------- Действия ----------
def is_in_battle(screen, battle_anchor):
    return find_template(screen, battle_anchor, BATTLE_ANCHOR_THRESHOLD) is not None


def fight_until_victory(device, battle_anchor, continue_template):
    for i in range(MAX_ATTACKS_PER_BATTLE):
        screen = get_screenshot(device)
        if screen is None:
            time.sleep(1)
            continue

        if not is_in_battle(screen, battle_anchor):
            print(f"  ✓ Бой завершён (ударов: {i})")
            find_continue_and_click(device, continue_template)
            return True

        print(f"  → Удар #{i+1}")
        tap(device, *ATTACK_BTN)
        time.sleep(DELAY_BETWEEN_ATTACKS)

    print(f"  ⚠ Лимит ударов исчерпан ({MAX_ATTACKS_PER_BATTLE})")
    return False


# ---------- Главный цикл ----------
def main():
    print("Подключаюсь к эмулятору...")
    device = connect()
    print("Подключено.")
    print(f"Разрешение: {device.shell('wm size').strip()}")

    # Шаблоны монстров
    print(f"Загружаю шаблоны монстров из '{TEMPLATES_DIR}/':")
    templates = load_templates(exclude=['battle_anchor.png', 'continue_button.png'])
    if not templates:
        print("Нет шаблонов монстров.")
        return

    # Якорь боя
    anchor_path = os.path.join(TEMPLATES_DIR, 'battle_anchor.png')
    battle_anchor = cv2.imread(anchor_path, cv2.IMREAD_COLOR)
    if battle_anchor is None:
        print(f"\nВНИМАНИЕ: не найден '{anchor_path}'.")
        return
    print(f"Якорь боя загружен: {battle_anchor.shape[1]}x{battle_anchor.shape[0]}")

    # Кнопка "Продолжить"
    continue_path = os.path.join(TEMPLATES_DIR, 'continue_button.png')
    continue_template = cv2.imread(continue_path, cv2.IMREAD_COLOR)
    if continue_template is None:
        print(f"\nВНИМАНИЕ: не найден '{continue_path}'.")
        print("Нарежьте кнопку 'Продолжить' и сохраните как continue_button.png")
        return
    print(f"Кнопка 'Продолжить' загружена: {continue_template.shape[1]}x{continue_template.shape[0]}")

    print("=" * 50)
    print("Бот запущен. Ctrl+C — остановка.")
    print("=" * 50)

    cycle = 0
    while True:
        cycle += 1
        try:
            screen = get_screenshot(device)
            if screen is None:
                time.sleep(1)
                continue

            # 1. Мы в бою?
            if is_in_battle(screen, battle_anchor):
                print(f"\n--- Цикл #{cycle}: в бою ---")
                fight_until_victory(device, battle_anchor, continue_template)
                continue

            # 2. Мы на карте — ищем монстра
            result = find_monster(screen, templates)
            if not result:
                print(f"--- Цикл #{cycle}: монстров нет ---")
                time.sleep(DELAY_IF_NO_MONSTER)
                continue

            x, y, name, conf = result
            print(f"\n--- Цикл #{cycle}: найден '{name}' ({x},{y}) conf={conf:.2f} ---")

            # 3. Клик по монстру
            tap(device, x, y)
            time.sleep(DELAY_AFTER_MONSTER_TAP)

            # 4. Клик "Начать бой"
            tap(device, *START_BATTLE_BTN)
            time.sleep(DELAY_AFTER_START_BATTLE)

        except KeyboardInterrupt:
            print("\nОстановлено.")
            break
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()