"""Welfare-only visual anchors. All coordinates are in the calibrated game crop."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
import numpy as np
from PIL import Image
from adapters.local_ocr import ReadOnlyController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.pipeline import JTemplateMatch

ASSETS = Path(__file__).resolve().parent / 'resources/local/welfare'
BASE_CLOSE = (1598, 134)
BUTTONS = {'monthly': (640, 752, 820, 830), 'large_monthly': (930, 752, 1110, 830),
           'medal_daily': (1230, 526, 1410, 607), 'medal_weekly': (1230, 744, 1410, 825),
           'online_1': (640, 722, 820, 808), 'online_2': (930, 722, 1110, 808),
           'online_3': (1230, 722, 1410, 808)}
TIERS = {'上忍': (1232, 629, 1290, 663), '中忍': (1290, 629, 1349, 663),
         '下忍': (1349, 629, 1409, 663)}


def load(name):
    path = ASSETS / (name + '.png') if name.startswith('reference-') else ASSETS / 'image' / (name + '.png')
    return np.array(Image.open(path).convert('RGB'))[:, :, ::-1].copy()


class WelfareVision:
    def __init__(self, ocr):
        self.ocr = ocr
        self.resource = Resource()
        if not self.resource.post_image(ASSETS / 'image').wait().succeeded:
            raise RuntimeError('福利大厅模板加载失败')
        self.controller = ReadOnlyController()
        self.controller.post_connection().wait()
        self.tasker = Tasker()
        self.tasker.bind(self.resource, self.controller)
        self.templates = {}

    def matches(self, image, name, threshold=.92):
        if name == 'entry':
            # The full reference includes the map behind the menu. Match only
            # the gift artwork plus its separate label, preserving the old box API.
            icons = self.matches(image, 'entry_icon', threshold)
            # Small outlined text includes map-coloured edge pixels. Allow a
            # 0.04 correlation margin only here; gift colour/score, pair geometry
            # and uniqueness still gate entry clicks.
            labels = self.matches(image, 'entry_label', threshold - .04)
            result = []
            for icon in icons:
                x, y, _, _ = icon['box']
                paired = [label for label in labels if
                          abs(label['box'][0]-(x-8)) <= 3 and abs(label['box'][1]-(y+66)) <= 3]
                if len(paired) == 1:
                    result.append({'box': [x-25, y-19, 109, 112],
                                   'score': min(icon['score'], paired[0]['score'])})
            return result
        if image.shape[:2] == (1015, 1920):
            regions = {'close': (1480, 30, 1740, 245),
                       'entry_icon': (1100, 100, 1600, 400), 'entry_label': (1100, 100, 1600, 400),
                       'daily_header': (500, 190, 950, 410), 'online_header': (850, 210, 1500, 450),
                       'daily_tab': (260, 230, 650, 460), 'daily_selected': (260, 230, 650, 460),
                       'online_tab': (260, 180, 650, 390), 'online_selected': (260, 180, 650, 390)}
            boxes = [regions[name]] if name in regions else [
                (x, y, min(x+640, 1920), min(y+420, 1015))
                for y in (0, 300, 600, 720) for x in (0, 480, 960, 1280)]
            result = []
            for l, t, r, b in boxes:
                for found in self.matches(image[t:b, l:r].copy(), name, threshold):
                    x, y, w, h = found['box']
                    box = [x+l, y+t, w, h]
                    if not any(abs(box[0]-m['box'][0]) < 20 and abs(box[1]-m['box'][1]) < 20 for m in result):
                        result.append(dict(found, box=box))
            return result
        self.controller.image = image
        detail = self.tasker.post_recognition('TemplateMatch', JTemplateMatch(
            template=[name+'.png'], threshold=[threshold]), image).wait().get()
        result = []
        if detail:
            for node in detail.nodes:
                if node.recognition:
                    for item in node.recognition.filtered_results:
                        box = list(item.box)
                        x, y, w, h = box
                        sample = image[y:y+h, x:x+w].astype(float)
                        if name not in self.templates:
                            self.templates[name] = load(name).astype(float)
                        reference = self.templates[name]
                        # Correlation alone also accepts a darkened background behind a modal,
                        # and can accept grey buttons. Require the original button colours.
                        if sample.shape != reference.shape or float(np.mean(np.abs(sample-reference))) > 28:
                            continue
                        if not any(abs(box[0]-m['box'][0]) < 20 and abs(box[1]-m['box'][1]) < 20 for m in result):
                            result.append({'box': box, 'score': float(item.score)})
        return result

    def unique(self, image, name):
        found = self.matches(image, name)
        if len(found) != 1:
            raise RuntimeError('福利大厅无法唯一识别：' + name)
        return found[0]['box']

    def panel(self, image, page=None):
        if image.shape[:2] != (1015, 1920):
            raise RuntimeError('福利大厅要求校准游戏区域1920×1015')
        x, y, w, h = self.unique(image, 'close')
        dx, dy = x+w//2-BASE_CLOSE[0], y+h//2-BASE_CLOSE[1]
        # Keep all action regions inside the game image.
        if abs(dx) > 80 or abs(dy) > 50:
            raise RuntimeError('福利大厅布局超出已验证范围')
        if page:
            self.unique(image, page + '_header')
            self.unique(image, page + '_selected')
        else:
            if not (self.matches(image, 'daily_tab') or self.matches(image, 'daily_selected')):
                raise RuntimeError('福利大厅导航未识别')
        return dx, dy

    def region(self, image, box, page):
        dx, dy = self.panel(image, page)
        l, t, r, b = box
        return image[t+dy:b+dy, l+dx:r+dx], (l+dx, t+dy)

    def button(self, image, slot):
        page = 'online' if slot.startswith('online') else 'daily'
        crop, (x, y) = self.region(image, BUTTONS[slot], page)
        # Medal buttons have a distinct border/letter rendering from month cards.
        template = 'claim_medal' if slot.startswith('medal_') else 'claim_' + page
        found = self.matches(crop, template, .92)
        if len(found) > 1:
            raise RuntimeError('领取按钮不唯一：' + slot)
        if found:
            l, t, w, h = found[0]['box']
            return {'state': 'claimable', 'point': (x+l+w//2, y+t+h//2)}
        received = self.matches(crop, 'received', .92)
        if len(received) == 1:
            return {'state': 'unavailable', 'text': '已领取（真实灰色按钮模板）', 'received': True}
        # Page and reward region are already verified. Only the active claim
        # template grants a click; recharge, purchase, grey or unreadable buttons
        # all advance to the next reward without relying on OCR vocabulary.
        return {'state': 'unavailable', 'text': '未匹配可点击的领取按钮，跳过', 'received': False}

    def tier(self, image):
        brightness = {}
        for name, box in TIERS.items():
            crop, _ = self.region(image, box, 'daily')
            brightness[name] = float(np.mean(crop))
        ordered = sorted(brightness, key=brightness.get, reverse=True)
        if brightness[ordered[0]] - brightness[ordered[1]] < 18:
            raise RuntimeError('无法确认勋章当前选中的忍者等级')
        return ordered[0]

    def tier_point(self, image, name):
        _, (x, y) = self.region(image, TIERS[name], 'daily')
        l, t, r, b = TIERS[name]
        return x+(r-l)//2, y+(b-t)//2
