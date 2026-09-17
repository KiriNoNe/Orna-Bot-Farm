from adb_shell.adb_device import AdbDeviceTcp
import time

ADB_HOST = '127.0.0.1'
ADB_PORT = 5555  # рабочий порт

def connect():
    device = AdbDeviceTcp(ADB_HOST, ADB_PORT, default_transport_timeout_s=9.)
    device.connect()
    return device

if __name__ == "__main__":
    device = connect()
    print("Подключено!")
    
    # Узнаем разрешение экрана — это критично для координат
    size = device.shell('wm size')
    print("Разрешение:", size)
    
    # Узнаем модель/версию Android
    print(device.shell('getprop ro.product.model'))