import cv2
import glob
import os
from bot import connect, get_screenshot, load_template, find_template_single

device = connect()
screen = get_screenshot(device)
cv2.imwrite("screenshots/debug_screen.png", screen)
print("Скриншот сохранён в screenshots/debug_screen.png")

# Перебираем все шаблоны и проверяем их при разных масштабах и порогах
templates = []
for path in sorted(glob.glob('templates/*.png')):
    name = os.path.basename(path)
    if name in ('battle_anchor.png', 'continue_button.png'):
        continue
    img = load_template(path)
    if img is not None:
        templates.append((name, img))

print(f"\nПроверяем {len(templates)} шаблонов на текущем экране:\n")

for name, template in templates:
    best_result = None
    for scale in [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]:
        new_w = int(template.shape[1] * scale)
        new_h = int(template.shape[0] * scale)
        resized = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        # Порог 0.0 — покажет РЕАЛЬНЫЙ conf без отсечения
        r = find_template_single(screen, resized, 0.0)
        if r:
            x, y, conf = r
            if best_result is None or conf > best_result[2]:
                best_result = (scale, (x, y), conf)
    
    if best_result:
        scale, (x, y), conf = best_result
        marker = "✓" if conf >= 0.6 else "·"
        print(f"  {marker} {name:50s} лучший: scale={scale:.2f} ({x},{y}) conf={conf:.3f}")