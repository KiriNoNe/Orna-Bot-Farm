import cv2
from bot import connect, get_screenshot, load_templates, find_monster

device = connect()
templates = load_templates()

print("Делаю скриншот...")
screen = get_screenshot(device)

if screen is None:
    print("Не удалось получить скриншот.")
    exit(1)

# Пробуем разные пороги
for thr in [0.85, 0.75, 0.65, 0.55, 0.45]:
    result = find_monster(screen, templates, threshold=thr)
    if result:
        x, y, name, conf = result
        print(f"Порог {thr}: НАЙДЕН '{name}' в ({x},{y}), conf={conf:.3f}")
        cv2.circle(screen, (x, y), 25, (0, 255, 0), 3)
    else:
        print(f"Порог {thr}: не найдено")

cv2.imshow("Debug match", screen)
cv2.waitKey(0)
cv2.destroyAllWindows()