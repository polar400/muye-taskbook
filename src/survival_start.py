"""Survival preparation start button; isolated from other tasks' templates."""
import re


def survival_start_button(flow):
    height, width = flow.image.shape[:2]
    candidates = [item for item in flow.items
                  if re.fullmatch(r'开战', re.sub(r'\s+', '', item['text']))
                  and item.get('score', 0) >= .8]
    candidates += flow.ocr.match(flow.image, 'survival_start', threshold=.94)
    candidates += flow.ocr.match(flow.image, 'start_battle')
    buttons = []
    for item in candidates:
        x, y, w, h = item['box']
        cx, cy = x + w / 2, y + h / 2
        if not (.35 * width <= cx <= .65 * width and .06 * height <= cy <= .25 * height):
            continue
        # OCR text and its enclosing template refer to the same button.
        if any(abs(cx - (b['box'][0] + b['box'][2] / 2)) <= 25
               and abs(cy - (b['box'][1] + b['box'][3] / 2)) <= 25 for b in buttons):
            continue
        buttons.append(item)
    if len(buttons) > 1:
        raise RuntimeError('生存演习开战按钮不唯一，停止')
    return buttons[0] if buttons else None


def start_survival_battle(flow):
    button = None

    def ready():
        nonlocal button
        button = survival_start_button(flow)
        return button is not None

    flow.wait(ready)
    flow.observe()
    fresh = survival_start_button(flow)
    if fresh is None:
        raise RuntimeError('生存演习开战按钮已变化，停止')
    x, y, w, h = button['box']
    fx, fy, fw, fh = fresh['box']
    if abs(x + w / 2 - fx - fw / 2) > 25 or abs(y + h / 2 - fy - fh / 2) > 25:
        raise RuntimeError('生存演习开战按钮位置已变化，停止')
    flow.click_item(fresh, delay=0)
