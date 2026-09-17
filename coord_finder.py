import cv2
import os
from adb_shell.adb_device import AdbDeviceTcp

ADB_HOST = '127.0.0.1'
ADB_PORT = 5555
DEVICE_SCREEN_PATH = '/sdcard/_bot_screen.png'
LOCAL_SCREEN_PATH = 'screenshots/_temp.png'

WINDOW = "Coord Finder | LMB=click | R=refresh | C=clear | Q=quit"

# Глобальные переменные модуля
current_screen = None
clicked_points = []  # список (x, y, label)


def connect():
    d = AdbDeviceTcp(ADB_HOST, ADB_PORT, default_transport_timeout_s=9.)
    d.connect()
    return d


def get_screenshot(device):
    device.shell(f'screencap -p {DEVICE_SCREEN_PATH}')
    os.makedirs('screenshots', exist_ok=True)
    device.pull(DEVICE_SCREEN_PATH, LOCAL_SCREEN_PATH)
    return cv2.imread(LOCAL_SCREEN_PATH)


def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        label = f"P{len(clicked_points) + 1}"
        clicked_points.append((x, y, label))
        print(f"[{label}] Координаты: X={x}, Y={y}")
        redraw()


def redraw():
    """Перерисовывает окно с метками всех кликов."""
    display = current_screen.copy()
    for (x, y, label) in clicked_points:
        cv2.circle(display, (x, y), 12, (0, 0, 255), 2)
        cv2.putText(display, label, (x + 15, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.imshow(WINDOW, display)


if __name__ == "__main__":
    device = connect()
    print("Подключено к эмулятору.")
    print(f"Разрешение экрана: {device.shell('wm size').strip()}")

    current_screen = get_screenshot(device)
    if current_screen is None:
        print("Не удалось получить скриншот.")
        exit(1)

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW, mouse_callback)
    redraw()

    while True:
        key = cv2.waitKey(50) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('r'):
            current_screen = get_screenshot(device)
            clicked_points.clear()
            print("--- Скриншот обновлён, метки очищены ---")
            redraw()
        elif key == ord('c'):
            clicked_points.clear()
            print("--- Метки очищены ---")
            redraw()

    cv2.destroyAllWindows()

    if clicked_points:
        print("\n=== Собранные координаты ===")
        for (x, y, label) in clicked_points:
            print(f"{label}: ({x}, {y})")