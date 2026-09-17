import cv2
import numpy as np
import os
from adb_shell.adb_device import AdbDeviceTcp

ADB_HOST = '127.0.0.1'
ADB_PORT = 5555

DEVICE_SCREEN_PATH = '/sdcard/_bot_screen.png'
LOCAL_SCREEN_PATH = 'screenshots/_temp.png'

def connect():
    d = AdbDeviceTcp(ADB_HOST, ADB_PORT, default_transport_timeout_s=9.)
    d.connect()
    return d

def get_screenshot(device):
    """Делает скриншот через файл: сохраняет на устройстве, скачивает, читает."""
    # 1. Делаем скриншот в файл на устройстве
    device.shell(f'screencap -p {DEVICE_SCREEN_PATH}')
    
    # 2. Скачиваем файл на ноутбук
    os.makedirs('screenshots', exist_ok=True)
    device.pull(DEVICE_SCREEN_PATH, LOCAL_SCREEN_PATH)
    
    # 3. Читаем через OpenCV
    screen = cv2.imread(LOCAL_SCREEN_PATH)
    return screen

if __name__ == "__main__":
    device = connect()
    print("Подключено.")
    print("Разрешение:", device.shell('wm size').strip())
    
    screen = get_screenshot(device)
    if screen is None:
        print("Не удалось получить скриншот!")
    else:
        print(f"Скриншот получен: {screen.shape[1]}x{screen.shape[0]}")
        cv2.imwrite("screenshots/first_shot.png", screen)
        cv2.imshow("Orna", screen)
        cv2.waitKey(0)
        cv2.destroyAllWindows()