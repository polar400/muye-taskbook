"""Ranked pilot on the real MaaFramework Tasker, with the existing window IO.

Only observations may retry. Actions never replay after an uncertain result.
Native waits have timeout=-1; the callbacks enforce finite *active-time* budgets
so pausing does not consume the wait budget. The OCR Tasker remains separate.
"""
import json
import time
from pathlib import Path

from adapters.local_ocr import ReadOnlyController
from local_flows import select_opponent
from ranked_policy import ranked_options
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.resource import Resource
from maa.tasker import Tasker

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'resources/maa_ranked'
LABELS = {
    'start':'检查当前页面', 'enter':'进入排位战', 'scope':'确认挑战范围',
    'scoped':'挑战范围已确认', 'stable':'复核剩余次数和战力',
    'decide':'检查进度和场数上限', 'challenge':'选择对手并挑战',
    'wait_battle':'等待战斗结束', 'end_button':'等待战斗结束',
    'end_battle':'结束战斗', 'settlement':'等待结算', 'result':'复核胜负',
    'confirm':'确认结算', 'returned':'确认返回挑战面板', 'panel':'等待挑战面板',
    'refresh':'检查战败后的刷新', 'refresh_notice':'确认免费刷新冷却提示',
    'refreshed':'确认刷新结果', 'close':'关闭排位面板', 'home':'等待木叶村主页',
    'finish':'排位战收尾完成', 'fail':'停止并保留失败证据',
}


class RankedSession:
    def __init__(self, flow):
        self.flow = flow
        self.server, self.limit = ranked_options(flow.cfg)
        self.original_checkpoint = flow.checkpoint
        self.paused_seconds = 0
        self.pause_epoch = 0
        self.qualified_epoch = 0
        self.frame_seq = 0
        self.observed_seq = -1
        self.error = None
        self.finished = False
        self.completed = 0
        self.count = None
        self.state = None
        self.previous = None
        self.before_challenge = None
        self.refresh_count = None
        self.refresh_old = None
        self.refresh_previous = None
        self.pending = None
        self.in_flight = False
        self.returned = False
        self.end_sent = False
        self.confirm_sent = False
        self.refresh_notice_sent = False
        self.scoped = False
        self.scope_stable = 0
        self.read_errors = {}
        self.wait_label = '检查当前页面'
        self.deadline = None
        self.clock = time.monotonic

    def checkpoint(self):
        begin = self.clock()
        try:
            self.original_checkpoint()
        finally:
            # The worker checkpoint only blocks for pause, not screenshot/OCR.
            blocked = self.clock() - begin
            self.paused_seconds += blocked
            if blocked >= .05:
                self.pause_epoch += 1

    def active_time(self):
        return self.clock() - self.paused_seconds

    def progress(self, name, status='running'):
        label = LABELS.get(name, name)
        message = f'排位战 · {label} · 已完成{self.completed}场'
        if self.count is not None:
            message += f'，剩余{self.count}次'
        if self.limit:
            message += f'（本轮最多{self.limit}场）'
        self.flow.emit('node', message, id='ranked', node=name, status=status,
                       completed=self.completed, remaining=self.count, limit=self.limit)

    def wait_for(self, name, seconds=30):
        self.wait_label = LABELS.get(name, name)
        self.deadline = self.active_time() + seconds
        self.previous = None
        self.read_errors.clear()
        self.progress(name)

    def guard(self):
        self.checkpoint()
        if self.error is not None:
            raise self.error

    def fresh(self):
        self.guard()
        self.flow.observe()
        self.observed_seq = -1
        self.qualified_epoch = self.pause_epoch

    def observe_frame(self, image):
        self.guard()
        if self.observed_seq != self.frame_seq:
            self.flow.image = image
            self.flow.items = self.flow.ocr.read(image)
            self.observed_seq = self.frame_seq
            self.qualified_epoch = self.pause_epoch
        if self.deadline is not None and self.active_time() > self.deadline:
            raise TimeoutError('排位战等待超时：' + self.wait_label + '，已保留最后截图')

    def remember_error(self, error):
        if self.error is None:
            self.error = error
            try:
                self.progress('已停止' if str(error)=='已停止' else self.wait_label,
                              'interrupted' if str(error)=='已停止' else 'failed')
            except Exception:
                pass  # Never let reporting mask the original callback error.

    def route(self, context, node, target):
        if not context.override_next(node, [target]):
            raise RuntimeError('排位战流水线后继配置失败：' + node)

    @staticmethod
    def signature(state):
        count, own, opponents = state
        return count, own, tuple(sorted(o['power'] for o in opponents))

    def recognize(self, name, image):
        # Capture/window failures are recorded by the controller and are fatal.
        self.guard()
        try:
            self.observe_frame(image)
            f = self.flow
            if name == 'panel':
                hit = f.ranked_panel_visible()
            elif name == 'scoped':
                valid = f.ranked_panel_visible() and f.ranked_server_state() == self.server
                self.scope_stable = self.scope_stable + 1 if valid else 0
                hit = self.scope_stable >= 2
            elif name == 'stable':
                if not f.ranked_panel_visible():
                    self.previous = None
                    return False
                state = f.ranked_state()
                current = self.signature(state)
                hit = current == self.previous and getattr(self,'previous_frame_seq',None)!=self.frame_seq
                self.previous = current
                self.previous_frame_seq = self.frame_seq
                if hit:
                    self.state = state
            elif name == 'settlement':
                hit = f.battle_settlement()
            elif name == 'end_button':
                hit = f.ranked_end_battle_button() is not None
            elif name == 'home':
                hit = bool(f.ocr.match(image, 'entry_survival') and f.ocr.match(image, 'entry_ranked'))
            elif name in ('refresh_notice', 'refreshed'):
                if f.hits(r'元宝|点券|付费|购买|支付|花费'):
                    raise ValueError('刷新对手出现付费提示，停止')
                notice = bool(f.hits(r'冷却|刷新.*(?:稍后|等待|秒|分钟)'))
                if name == 'refresh_notice':
                    hit = notice and not self.refresh_notice_sent and len(f.hits(r'^(确定|确认)$')) == 1
                elif notice and f.hits(r'^(确定|确认)$'):
                    hit = False  # A stuck acknowledgement must not be clicked twice.
                elif f.ranked_panel_visible():
                    state, _ = f.ranked_refresh_state()
                    if state == 'cooldown':
                        hit = True
                    else:
                        powers = self.signature(f.ranked_state())[2]
                        hit = powers != self.refresh_old and powers == self.refresh_previous
                        self.refresh_previous = powers
                else:
                    hit = False
            else:
                raise ValueError('未知排位战识别状态：' + name)
            if hit:
                self.read_errors.pop(name, None)
            return bool(hit)
        except RuntimeError as error:
            # Read-only failures get three observations; never replay an action.
            self.previous = None
            self.scope_stable = 0
            attempts = self.read_errors.get(name, 0) + 1
            self.read_errors[name] = attempts
            if attempts >= 3:
                raise RuntimeError(f'排位战{LABELS[name]}连续3次识别失败：{error}') from error
            self.flow.log(f'排位战{LABELS[name]}重新识别 {attempts}/3：{error}')
            return False

    def read_result(self):
        # This only rereads the settlement. It never sends confirmation.
        for attempt in range(3):
            self.fresh()
            self.flow._settlement_scan_at = 0
            if not self.flow.battle_settlement():
                raise RuntimeError('排位战结算页面已变化，停止确认')
            try:
                return self.flow.ranked_battle_result()
            except RuntimeError:
                if attempt == 2:
                    raise
                self.flow.log(f'排位战胜负重新识别 {attempt+1}/3，保留结算弹窗')
        raise RuntimeError('排位战胜负未确认')

    def action(self, op, context, node):
        self.guard()
        self.progress(op)
        f = self.flow
        if op == 'start':
            self.fresh()
            if f.ranked_panel_visible():
                self.wait_for('panel')
                self.route(context, node, 'RankedPanel')
            elif f.ranked_end_battle_button() is not None or f.battle_settlement():
                self.in_flight = True
                f.log('接续已有排位战战斗或结算，本轮计入一场；未重复发起挑战')
                self.route(context, node, 'RankedWaitBattle')
            else:
                self.route(context, node, 'RankedEnter')
        elif op == 'enter':
            f.enter('排位战')
            self.wait_for('panel')
        elif op == 'scope':
            self.fresh()
            if f.ranked_server_state() == self.server:
                self.scoped = True
                self.wait_for('stable')
                self.route(context, node, 'RankedRead')
            else:
                f.click_item(f.ranked_server_button(self.server))
                self.scope_stable = 0
                self.wait_for('scoped')
                self.route(context, node, 'RankedScoped')
        elif op == 'scoped':
            self.scoped = True
            self.wait_for('stable')
        elif op == 'decide':
            count, _, _ = self.state
            self.count = count
            if self.before_challenge is not None:
                if count != self.before_challenge - 1:
                    raise RuntimeError('挑战次数未按一场减少，停止以避免重复挑战')
                self.before_challenge = None
            if self.refresh_count is not None:
                if count != self.refresh_count:
                    raise RuntimeError('刷新后挑战次数变化异常，停止')
                self.refresh_count = None
            if self.returned:
                self.completed += 1
                self.in_flight = False
                self.returned = False
            if self.completed >= 30 and count > 0 and (not self.limit or self.completed < self.limit):
                raise RuntimeError('排位战达到循环上限，停止')
            if count == 0 or self.limit and self.completed >= self.limit:
                target = 'RankedClose'
            elif self.pending == 'defeat':
                target = 'RankedRefresh'
            else:
                target = 'RankedChallenge'
            self.route(context, node, target)
        elif op == 'challenge':
            if self.in_flight or self.before_challenge is not None:
                raise RuntimeError('上一场挑战尚未核实，拒绝重复发起')
            self.fresh()
            state = f.ranked_state()
            if self.signature(state) != self.signature(self.state):
                raise RuntimeError('挑战前次数或对手已变化，停止')
            count, own, opponents = state
            picked = select_opponent(own, opponents, f.cfg.get('tolerance', 20))
            f.log(f'我方战力 {own}，选择对手 {picked["power"]}，战力差 {abs(picked["power"]-own)/own:.1%}')
            # Set the ledger before delivering the input: an uncertain send is never retried.
            self.before_challenge = count
            self.in_flight = True
            self.end_sent = self.confirm_sent = False
            f.click_item(picked['button'])
        elif op == 'wait_battle':
            f._settlement_scan_at = 0
            self.wait_for('end_button', 120)
        elif op == 'end_battle':
            self.fresh()
            f._settlement_scan_at = 0
            # override_next persists in the native Context. A previous missed
            # frame enabled a self-loop; retire it before any successful send
            # so lingering battle controls cannot replay this action.
            self.route(context, node, 'RankedSettlement')
            if not f.battle_settlement():
                button = f.ranked_end_battle_button()
                if self.end_sent:
                    raise RuntimeError('结束战斗已发送，拒绝重复点击')
                if button is None:
                    # Recognition can be followed by an animation frame with
                    # no hit. Nothing has been sent: reobserve both successors
                    # without restarting the original finite wait deadline.
                    f.log('结束战斗按钮暂未稳定，继续只读等待；未发送点击')
                    if not context.override_next(node,['RankedSettlement','RankedEndButton']):
                        raise RuntimeError('排位战流水线后继配置失败：'+node)
                    return True
                self.end_sent = True
                f.log('已复核右下角结束战斗按钮，发送一次后台点击')
                f.click_item(button)
            self.wait_for('settlement', f.cfg.get('battleSeconds', 900))
        elif op == 'result':
            self.pending = self.read_result()
            f.log('排位战结算：' + ('胜利' if self.pending == 'victory' else '失败'))
        elif op == 'confirm':
            if self.confirm_sent or not self.in_flight:
                raise RuntimeError('结算已确认或缺少在途战斗，拒绝重复确认')
            if self.read_result() != self.pending:
                raise RuntimeError('排位战胜负复核不一致，停止确认')
            self.confirm_sent = True
            def same_settlement():
                f._settlement_scan_at = 0
                return f.battle_settlement() and f.ranked_battle_result() == self.pending
            f.confirm(guard=same_settlement)
            self.wait_for('returned')
        elif op == 'returned':
            if not self.in_flight or not self.confirm_sent:
                raise RuntimeError('缺少已确认结算，不能计入完成场数')
            self.returned = True
            self.wait_for('stable' if self.scoped else 'panel')
            self.route(context, node, 'RankedRead' if self.scoped else 'RankedPanel')
        elif op == 'refresh':
            if self.pending != 'defeat' or self.limit and self.completed >= self.limit:
                raise RuntimeError('未确认战败或已达到上限，拒绝刷新')
            self.fresh()
            count, _, _ = f.ranked_state()
            if count != self.count:
                raise RuntimeError('刷新前挑战次数已变化，停止')
            self.refresh_count = count
            state, button = f.ranked_refresh_state()
            if state == 'cooldown':
                f.log('刷新对手正在冷却，继续按原规则挑战')
                self.pending = None
                self.wait_for('stable')
                self.route(context, node, 'RankedRead')
            elif state == 'ready':
                self.refresh_old = self.signature(f.ranked_state())[2]
                self.refresh_previous = None
                self.refresh_notice_sent = False
                f.click_item(button)
                self.wait_for('refreshed', 15)
            else:
                raise RuntimeError('无法确认刷新按钮或冷却状态，停止')
        elif op == 'refresh_notice':
            if self.refresh_notice_sent:
                raise RuntimeError('刷新冷却提示已确认，拒绝重复点击')
            self.fresh()
            if not f.hits(r'冷却|刷新.*(?:稍后|等待|秒|分钟)'):
                raise RuntimeError('刷新冷却提示已变化，停止确认')
            self.refresh_notice_sent = True
            f.confirm(guard=lambda:bool(f.hits(r'冷却|刷新.*(?:稍后|等待|秒|分钟)')))
            # Keep the original finite refresh deadline.
        elif op == 'refreshed':
            self.pending = None
            self.wait_for('stable')
        elif op == 'close':
            if self.in_flight or self.before_challenge is not None:
                raise RuntimeError('挑战进度尚未核实，不能关闭任务')
            if self.count is None or not (self.count == 0 or self.limit and self.completed >= self.limit):
                raise RuntimeError('尚未满足排位战结束条件')
            f.close_panel(check_home=False)
            self.wait_for('home')
        elif op == 'finish':
            self.finished = True
            self.progress('finish', 'done')
        elif op == 'fail':
            raise self.error or RuntimeError('排位战流水线失败：' + self.wait_label)
        else:
            raise ValueError('未知排位战动作：' + op)
        return True


class RankedController(ReadOnlyController):
    """Only forwards capture; native Click/key actions remain denied."""
    def __init__(self, session):
        self.session = session
        super().__init__()
        self.set_screenshot_use_raw_size(True)

    def request_uuid(self):
        return 'naruto-ranked-background'

    def screencap(self):
        try:
            self.session.guard()
            image = self.session.flow.capture_ready()
            self.session.flow.image = image
            self.session.flow.window.save(image, ROOT/'verification/background-latest.png')
            self.session.frame_seq += 1
            return image
        except Exception as error:
            self.session.remember_error(error)
            # No exception escapes the ctypes callback boundary.
            import numpy as np
            return np.zeros((2, 2, 3), dtype=np.uint8)


class RankedWindow:
    """Keep the exact backend, but reject a click qualified before a pause."""
    def __init__(self, session, backend):
        self.session = session
        self.backend = backend

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def click(self, x, y):
        self.session.guard()
        if self.session.pause_epoch != self.session.qualified_epoch:
            raise RuntimeError('暂停后点击依据已过期，请重新开始以复核当前页面')
        return self.backend.click(x, y)


class RankedAction(CustomAction):
    def __init__(self, session):
        self.session = session
        super().__init__()

    def run(self, context, argv):
        try:
            op = json.loads(argv.custom_action_param)['op']
            return bool(self.session.action(op, context, argv.node_name))
        except Exception as error:
            self.session.remember_error(error)
            return False


class RankedRecognition(CustomRecognition):
    def __init__(self, session):
        self.session = session
        super().__init__()

    def analyze(self, context, argv):
        try:
            state = json.loads(argv.custom_recognition_param)['state']
            if self.session.recognize(state, argv.image):
                return self.AnalyzeResult(box=(0, 0, 1, 1), detail={'state':state})
            return None
        except Exception as error:
            self.session.remember_error(error)
            return None


def run_ranked_pipeline(flow, *, pipeline_override=None):
    session = RankedSession(flow)
    resource = Resource()
    # Explicit loading also avoids this bundled DLL's crashing directory loader.
    # This is the official Resource API, not an alternative Python executor.
    nodes = json.loads((BUNDLE/'pipeline/ranked.json').read_text(encoding='utf-8'))
    if not resource.override_pipeline(nodes) or not resource.post_image(ROOT/'resources/local/image').wait().succeeded:
        raise RuntimeError('排位战流水线资源加载失败')
    if not resource.register_custom_action('RankedAction', RankedAction(session)):
        raise RuntimeError('排位战动作注册失败')
    if not resource.register_custom_recognition('RankedRecognition', RankedRecognition(session)):
        raise RuntimeError('排位战识别注册失败')
    controller = RankedController(session)
    if not controller.post_connection().wait().succeeded:
        raise RuntimeError('排位战后台适配连接失败')
    tasker = Tasker()
    if not tasker.bind(resource, controller) or not tasker.inited:
        raise RuntimeError('排位战执行器初始化失败')
    flow.checkpoint = session.checkpoint
    original_window = flow.window
    original_observe = flow.observe
    flow.window = RankedWindow(session, original_window)
    def observe():
        result = original_observe()
        session.observed_seq = -1
        session.qualified_epoch = session.pause_epoch
        return result
    flow.observe = observe
    job = None
    try:
        job = tasker.post_task('RankedStart', pipeline_override or {})
        stopping = False
        while not job.done:
            if session.error is not None and not stopping:
                tasker.post_stop()
                stopping = True
            time.sleep(.025)
        job.wait()
        if session.error is not None:
            raise session.error
        if not job.succeeded or not session.finished:
            raise RuntimeError('排位战流水线未完成：' + session.wait_label)
        return 'skipped' if session.completed == 0 else None
    finally:
        if job is not None and not job.done:
            tasker.post_stop().wait()
        flow.checkpoint = session.original_checkpoint
        flow.window = original_window
        flow.observe = original_observe
