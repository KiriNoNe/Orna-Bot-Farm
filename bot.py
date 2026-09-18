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
HEAL_BTN         = (959, 817)   # НОВОЕ: кнопка "похилить" (long press)

# ---------- Пороги ----------
MONSTER_THRESHOLD       = 0.6
BATTLE_ANCHOR_THRESHOLD = 0.75
CONTINUE_THRESHOLD      = 0.75

# ---------- Мультимасштаб для монстров ----------
# Спрайты с сайта 24x24, в игре монстры ~48x48
MONSTER_SCALES = [2.0]

# ---------- Чёрный список точек, где клик не сработал ----------
SKIP_RADIUS = 40        # если новая точка ближе этого к "битой" — пропускаем
SKIP_CYCLES = 30        # сколько циклов помнить битую точку
skip_list = []          # [(x, y, expire_cycle), ...]

# ---------- Паузы (секунды) ----------
DELAY_AFTER_MONSTER_TAP  = 1.0
DELAY_AFTER_START_BATTLE = 2.0
DELAY_BETWEEN_ATTACKS    = 3.0
DELAY_AFTER_CONTINUE     = 1    # было 1.0 → чуть уменьшим
DELAY_AFTER_HEAL         = 1      # было 1.5 → чуть уменьшим
DELAY_IF_NO_MONSTER      = 1.0
MAX_ATTACKS_PER_BATTLE   = 30
MAX_CONTINUE_WAIT        = 10       # для ПЕРВОГО раунда
QUICK_CONTINUE_WAIT      = 1        # НОВОЕ: для последующих раундов (2 × 0.5 = 1 сек)
MAX_CONTINUE_ROUNDS      = 3
HEAL_HOLD_MS             = 1000


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


def long_press(device, x, y, duration_ms=1000):
    """Долгое нажатие: свайп из точки в ту же точку с заданной длительностью."""
    device.shell(f'input swipe {x} {y} {x} {y} {duration_ms}')


# ---------- Загрузка шаблонов ----------
def load_template(path):
    """Загружает PNG с альфа-каналом, если он есть."""
    return cv2.imread(path, cv2.IMREAD_UNCHANGED)


def load_templates(exclude=None):
    exclude = exclude or []
    templates = []
    for path in sorted(glob.glob(os.path.join(TEMPLATES_DIR, '*.png'))):
        name = os.path.basename(path)
        if name in exclude:
            continue
        img = load_template(path)
        if img is not None:
            templates.append((name, img))
            print(f"  Загружен: {name} {img.shape[1]}x{img.shape[0]}")
    return templates


# ---------- Распознавание ----------
def find_template_single(screen, template, threshold):
    """
    Ищет шаблон (numpy-массив, BGR или BGRA) на скриншоте.
    Возвращает (x, y, conf) или None.
    """
    if template is None:
        return None
    if template.shape[0] > screen.shape[0] or template.shape[1] > screen.shape[1]:
        return None

    # Если есть альфа-канал — накладываем на серый фон (убираем прозрачность)
    if len(template.shape) == 3 and template.shape[2] == 4:
        alpha = template[:, :, 3:4].astype(np.float32) / 255.0
        color = template[:, :, :3].astype(np.float32)
        gray_bg = np.full_like(color, 128, dtype=np.float32)
        composite = (color * alpha + gray_bg * (1.0 - alpha)).astype(np.uint8)
        template_bgr = composite
    else:
        template_bgr = template if len(template.shape) == 3 else cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)

    # TM_CCOEFF_NORMED не срабатывает на однотонных участках
    res = cv2.matchTemplate(screen, template_bgr, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        h, w = template_bgr.shape[:2]
        return (max_loc[0] + w // 2, max_loc[1] + h // 2, max_val)
    return None


def find_template_multiscale(screen, template, threshold, scales):
    """
    Ищет шаблон (numpy) в нескольких масштабах.
    Возвращает лучший (x, y, conf) или None.
    """
    if template is None:
        return None

    best = None
    for scale in scales:
        new_w = int(template.shape[1] * scale)
        new_h = int(template.shape[0] * scale)
        if new_w < 5 or new_h < 5:
            continue
        if new_h > screen.shape[0] or new_w > screen.shape[1]:
            continue

        resized = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        r = find_template_single(screen, resized, threshold)
        if r:
            x, y, conf = r
            if best is None or conf > best[2]:
                best = (x, y, conf)
    return best


def is_position_skipped(x, y, current_cycle):
    """Проверяет, входит ли точка в чёрный список."""
    for sx, sy, expire in skip_list:
        if expire < current_cycle:
            continue
        if abs(sx - x) < SKIP_RADIUS and abs(sy - y) < SKIP_RADIUS:
            return True
    return False


def mark_position_bad(x, y, current_cycle):
    """Добавляет точку в чёрный список на SKIP_CYCLES циклов."""
    skip_list.append((x, y, current_cycle + SKIP_CYCLES))
    print(f"  ⛔ Точка ({x},{y}) в чёрном списке на {SKIP_CYCLES} циклов")


def try_engage_monster(device, x, y, battle_anchor, current_cycle):
    """Пытается начать бой. Возвращает True, если бой реально начался."""
    tap(device, x, y)
    time.sleep(DELAY_AFTER_MONSTER_TAP)
    tap(device, *START_BATTLE_BTN)
    time.sleep(DELAY_AFTER_START_BATTLE)

    screen = get_screenshot(device)
    if screen is None:
        return False
    if is_in_battle(screen, battle_anchor):
        return True

    # Клик не сработал — помечаем точку
    mark_position_bad(x, y, current_cycle)
    return False

def find_monster(screen, templates, current_cycle, threshold=MONSTER_THRESHOLD):
    """Ищет лучшего монстра, игнорируя точки из чёрного списка."""
    best = None
    for name, template in templates:
        r = find_template_multiscale(screen, template, threshold, MONSTER_SCALES)
        if not r:
            continue
        mx, my, conf = r

        # Пропускаем точки из чёрного списка
        if is_position_skipped(mx, my, current_cycle):
            continue

        if best is None or conf > best[0]:
            best = (conf, mx, my, name)

    if best is None:
        return None
    conf, x, y, name = best
    return (x, y, name, conf)


# ---------- Действия ----------
def is_in_battle(screen, battle_anchor):
    return find_template_single(screen, battle_anchor, BATTLE_ANCHOR_THRESHOLD) is not None


def find_continue_and_click(device, continue_template):
    total_clicks = 0
    for round_num in range(MAX_CONTINUE_ROUNDS):
        found_in_round = False
        for attempt in range(MAX_CONTINUE_WAIT):
            screen = get_screenshot(device)
            if screen is None:
                time.sleep(0.5)
                continue
            result = find_template_single(screen, continue_template, CONTINUE_THRESHOLD)
            if result:
                x, y, conf = result
                total_clicks += 1
                print(f"  → 'Продолжить' #{total_clicks} ({x},{y}) conf={conf:.2f}")
                tap(device, x, y)
                time.sleep(DELAY_AFTER_CONTINUE)
                found_in_round = True
                break
            time.sleep(0.5)

        if not found_in_round:
            if round_num == 0:
                print("  ⚠ Кнопка 'Продолжить' не появилась")
                return False
            else:
                print(f"  ✓ Все экраны закрыты. Кликов: {total_clicks}")
                return True

    print(f"  ⚠ Лимит раундов ({MAX_CONTINUE_ROUNDS})")
    return False


def fight_until_victory(device, battle_anchor, continue_template):
    for i in range(MAX_ATTACKS_PER_BATTLE):
        screen = get_screenshot(device)
        if screen is None:
            time.sleep(1)
            continue
        if not is_in_battle(screen, battle_anchor):
            print(f"  ✓ Бой завершён (ударов: {i})")
            find_continue_and_click(device, continue_template)

            # НОВОЕ: долгое нажатие на кнопку "похилить"
            print(f"  → Зажимаю кнопку хила {HEAL_BTN} на {HEAL_HOLD_MS} мс")
            long_press(device, *HEAL_BTN, duration_ms=HEAL_HOLD_MS)
            time.sleep(DELAY_AFTER_HEAL)

            return True
        print(f"  → Удар #{i+1}")
        tap(device, *ATTACK_BTN)
        time.sleep(DELAY_BETWEEN_ATTACKS)
    print(f"  ⚠ Лимит ударов ({MAX_ATTACKS_PER_BATTLE})")
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
    battle_anchor = load_template(anchor_path)
    if battle_anchor is None:
        print(f"\nВНИМАНИЕ: не найден '{anchor_path}'.")
        return
    print(f"Якорь боя: {battle_anchor.shape[1]}x{battle_anchor.shape[0]}")

    # Кнопка "Продолжить"
    continue_path = os.path.join(TEMPLATES_DIR, 'continue_button.png')
    continue_template = load_template(continue_path)
    if continue_template is None:
        print(f"\nВНИМАНИЕ: не найден '{continue_path}'.")
        return
    print(f"Кнопка 'Продолжить': {continue_template.shape[1]}x{continue_template.shape[0]}")

    print("=" * 50)
    print(f"Порог монстров: {MONSTER_THRESHOLD}")
    print(f"Масштабы: {MONSTER_SCALES}")
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
            result = find_monster(screen, templates, cycle)
            if not result:
                print(f"--- Цикл #{cycle}: монстров нет ---")
                time.sleep(DELAY_IF_NO_MONSTER)
                continue

            x, y, name, conf = result
            print(f"\n--- Цикл #{cycle}: найден '{name}' ({x},{y}) conf={conf:.2f} ---")

            # 3. Пробуем начать бой — с проверкой
            success = try_engage_monster(device, x, y, battle_anchor, cycle)
            if not success:
                print(f"  ✗ Бой не начался, ищем другую цель")
                time.sleep(0.5)
                continue

        except KeyboardInterrupt:
            print("\nОстановлено.")
            break
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()