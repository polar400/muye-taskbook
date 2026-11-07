"""One bounded welfare run, using the existing background window contract."""
import json
from pathlib import Path
import time
from datetime import datetime, timezone, timedelta
import uuid

from welfare_vision import WelfareVision


def centre(box):
    x, y, w, h = box
    return x+w//2, y+h//2


class WelfareTask:
    def __init__(self, window, ocr, folder, checkpoint=lambda: None, emit=print, vision=None):
        self.window, self.ocr = window, ocr
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.checkpoint, self.emit = checkpoint, emit
        self.vision = vision or WelfareVision(ocr)
        self.report = {'status': 'running', 'actions': [], 'rewards': [], 'gameInputs': 0}
        self.sequence = 0
        self.last_image = None
        self.clock = lambda: time.monotonic()

    def observe(self):
        self.checkpoint()
        image = self.window.capture()
        self.last_image = image
        self.sequence += 1
        self.window.save(image, self.folder / f'{self.sequence:03d}.png')
        return image

    def stable(self, reader):
        first = reader(self.observe())
        self.pause(.2)
        second = reader(self.observe())
        if first != second:
            raise RuntimeError('福利大厅连续两帧状态不一致，停止操作')
        return second

    def pause(self, seconds):
        end = self.clock()+seconds
        while self.clock() < end:
            self.checkpoint()
            time.sleep(min(.1, max(0, end-self.clock())))

    def wait(self, reader, expected, seconds=10):
        end = self.clock()+seconds
        last = None
        while self.clock() < end:
            self.checkpoint()
            try:
                value = reader(self.observe())
                if value == expected:
                    self.pause(.2)
                    if reader(self.observe()) == expected:
                        return
            except RuntimeError as error:
                last = str(error)
            self.pause(.3)
        raise RuntimeError('福利大厅输入后反馈未确认；不重复点击：'+str(last or expected))

    def send(self, label, reader):
        point = self.stable(reader)
        self.checkpoint()
        if reader(self.observe()) != point:
            raise RuntimeError('福利大厅发送前状态变化：'+label)
        action = {'label': label, 'point': list(point), 'state': 'attempted', 'beforeFrame': self.sequence}
        self.report['actions'].append(action)
        self.report['gameInputs'] += 1
        self.flush()
        # Record an attempt before sending: a partial down/up failure is never replayed.
        self.window.click(*point)
        action['state'] = 'sent'
        self.emit(label)
        self.flush()

    def flush(self):
        (self.folder / 'report.json').write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding='utf-8')

    def page(self, image, name):
        self.vision.panel(image, name)
        return name

    def goto(self, name):
        try:
            if self.stable(lambda im: self.page(im, name)) == name:
                return
        except RuntimeError:
            pass
        def target(image):
            self.vision.panel(image)
            return centre(self.vision.unique(image, name+'_tab'))
        self.send('打开'+('每日福利' if name == 'daily' else '在线礼包'), target)
        self.wait(lambda im: self.page(im, name), name)

    def home(self, image):
        if self.vision.matches(image, 'close'):
            raise RuntimeError('福利大厅尚未关闭')
        if not (self.ocr.match(image, 'entry_survival') and self.ocr.match(image, 'entry_ranked')):
            raise RuntimeError('未确认木叶村主页')
        return 'home'

    def open(self):
        image = self.observe()
        if self.vision.matches(image, 'close'):
            self.stable(lambda im: self.vision.panel(im))
            return
        def target(image):
            self.home(image)
            return centre(self.vision.unique(image, 'entry'))
        self.send('打开福利大厅', target)
        self.wait(lambda im: bool(self.vision.panel(im) is not None), True)

    def claim(self, slot, tier=None):
        reader = lambda im: self.vision.button(im, slot)
        state = self.stable(reader)
        result = {'slot': slot, 'tier': tier}
        if state['state'] == 'unavailable':
            result.update(status='unavailable', reason=state.get('text'))
        else:
            def target(image):
                if tier and self.vision.tier(image) != tier:
                    raise RuntimeError('勋章等级已变化')
                current = reader(image)
                if current['state'] != 'claimable':
                    raise RuntimeError('领取按钮状态已变化')
                return current['point']
            self.send('领取 '+slot+(' '+tier if tier else ''), target)
            after = {}
            def changed(image):
                after.clear()
                after.update(reader(image))
                return after['state']
            self.wait(changed, 'unavailable')
            # A non-claim button allows progress, but is not proof of a receipt.
            result['status'] = 'claimed_confirmed' if after.get('received') else 'claim_sent'
        result['afterFrame'] = self.sequence
        self.report['rewards'].append(result)
        self.flush()

    def select_tier(self, name):
        current = self.stable(self.vision.tier)
        if current != name:
            def target(image):
                if self.vision.tier(image) != current:
                    raise RuntimeError('勋章等级发送前变化')
                return self.vision.tier_point(image, name)
            self.send('查看勋章 '+name, target)
            self.wait(self.vision.tier, name)

    def run(self):
        try:
            self.open()
            self.goto('daily')
            for slot in ('monthly', 'large_monthly', 'medal_daily'):
                self.claim(slot)
            for tier in ('上忍', '中忍', '下忍'):
                self.select_tier(tier)
                self.claim('medal_weekly', tier)
            self.goto('online')
            for slot in ('online_1', 'online_2', 'online_3'):
                self.claim(slot)
            def close(image):
                self.vision.panel(image, 'online')
                return centre(self.vision.unique(image, 'close'))
            self.send('关闭福利大厅', close)
            self.wait(self.home, 'home')
            self.report['status'] = 'done'
            self.emit('福利大厅流程完成：已确认返回主页')
            return self.report
        except Exception as error:
            self.report.update(status='stopped', error=str(error))
            raise
        finally:
            self.flush()


def run_welfare(flow):
    """Daily-queue bridge: reuse the worker window, OCR, control and logging."""
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    folder = Path(__file__).resolve().parents[1]/'verification'/('welfare-'+stamp+'-'+uuid.uuid4().hex[:8])
    # Exclude time spent inside the host's blocking pause checkpoint from deadlines.
    blocked = 0.0
    def checkpoint():
        nonlocal blocked
        start = time.monotonic()
        try:
            flow.checkpoint()
        finally:
            blocked += time.monotonic()-start
    task = WelfareTask(flow.window, flow.ocr, folder, checkpoint, flow.log)
    task.clock = lambda: time.monotonic()-blocked
    flow.log('福利大厅证据目录：'+str(folder))
    try:
        report = task.run()
        if report.get('status') != 'done':
            raise RuntimeError('福利大厅未确认收尾')
        return 'completed'
    finally:
        flow.welfare_report = task.report
        if task.last_image is not None:
            flow.image = task.last_image
