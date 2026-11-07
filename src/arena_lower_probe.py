"""Bounded two-click acceptance harness; never invoked by the normal arena task."""
from copy import deepcopy
import time

from arena_daily import board_key


class LowerOnceProbe:
    def __init__(self,runner,pointers,save,*,clock=time.monotonic,sleep=time.sleep):
        self.runner=runner;self.window=runner.f.window;self.pointers=iter(pointers)
        self.save=save;self.clock=clock;self.sleep=sleep
        self.report=dict(result='preparing',inputs=[],phases=[],realMouseInputs=0)
        self.active_phase=None

    def observe(self,label):
        flow=self.runner.f
        start=self.clock();flow.image=self.window.capture();captured=self.clock()
        flow.items=flow.ocr.read(flow.image);recognized=self.clock()
        if self.active_phase is not None:
            self.active_phase.setdefault('observations',[]).append(dict(label=label,
                captureSeconds=captured-start,ocrSeconds=recognized-captured))
        self.save(label,self.report)
        if self.active_phase is not None:
            self.active_phase['observations'][-1]['saveSeconds']=self.clock()-recognized

    def read_until(self,label,reader,seconds=4):
        deadline=self.clock()+seconds
        while True:
            self.observe(label)
            value=reader()
            if self.clock()>deadline:raise TimeoutError('诊断读取超时：'+label)
            if value is not None and value is not False:return value
            self.sleep(.1)

    def stable_board(self,label,predicate=lambda board:True):
        last=None;frames=0
        def read():
            nonlocal last,frames
            board=self.runner.board()
            if board is None or not predicate(board):last=None;frames=0;return None
            key=board_key(board);frames=frames+1 if key==last else 1;last=key
            return board if frames>=2 else None
        return self.read_until(label,read)

    def click_once(self,label,target,reader):
        """One short override, one move, fresh recognition, at most one click."""
        pointer=next(self.pointers)
        x,y,w,h=target['box'];point=(x+w//2,y+h//2)
        phase=dict(label=label,point=list(point),restored=False)
        self.report['phases'].append(phase)
        # Start conservatively before prepare: the native five-second clock is
        # created later. Shared click can spend 3 x 1s in SendMessageTimeout.
        started=self.clock()
        self.active_phase=phase
        try:
            pointer.prepare(*point);phase['prepareSeconds']=self.clock()-started
            phase['shim']=deepcopy(pointer.evidence)
            try:
                with pointer.transaction:
                    self.window.hover(*point)
                    def checked():
                        began=self.clock();fresh=reader()
                        phase.setdefault('reads',[]).append(dict(seconds=self.clock()-began,
                            elapsed=self.clock()-started,found=bool(fresh)))
                        if self.clock()-started>1.7:
                            raise TimeoutError('虚拟指针剩余时间不足以安全发送一次后台点击')
                        if fresh:
                            bx,by,bw,bh=fresh['box']
                            if not bx<=point[0]<bx+bw or not by<=point[1]<by+bh:
                                raise RuntimeError('虚拟指针与新识别按钮位置不一致，未点击')
                        return fresh
                    self.read_until(label,checked,seconds=1.7)
                    if self.clock()-started>1.7:raise TimeoutError('点击前虚拟指针已临近失效')
                    event=dict(label=label,point=list(point),status='sending')
                    self.report['inputs'].append(event);self.save(label+'-input',self.report)
                    if self.clock()-started>1.7:
                        event['status']='not-sent'
                        raise TimeoutError('写入证据后虚拟指针已临近失效')
                    self.window.click(*point)
                    event['status']='sent'
            finally:
                phase['restored']=all(pointer.memory.read(e['address'],4).hex()==e['original']
                                      for e in pointer.evidence['entries'])
                if not phase['restored']:raise RuntimeError('虚拟指针入口恢复未确认，停止')
        finally:
            pointer.close();phase['totalSeconds']=self.clock()-started
            self.active_phase=None;self.save(label+'-restored',self.report)

    def run(self):
        try:
            before=self.stable_board('before');self.report['boardBefore']=before
            card=next((c for c in before['cards'] if c['state']=='unmet' and c['progress']==0),None)
            if card is None:raise RuntimeError('没有未满足0/1任务；未发送输入')
            self.click_once('open-lower',card['button'],
                lambda:self.runner.fresh_card(before,card['index'],'unmet',hovered=True))
            button=self.read_until('dialog',self.runner.lower_dialog)
            self.report['confirmation']=button
            # A second newly captured dialog is required inside the second
            # override. Cost or ambiguous text raises before confirmation.
            self.click_once('confirm-lower',button,self.runner.lower_dialog)
            after=self.stable_board('after',lambda b:board_key(b)!=board_key(before))
            if before['remaining']!=after['remaining']:
                raise RuntimeError('降级后任务数量发生变化，不能报告验收通过')
            if len(before['cards'])!=len(after['cards']):raise RuntimeError('降级后可见任务数量异常变化')
            if any((old['description'],old['state'],old['progress'])!=
                   (new['description'],new['state'],new['progress'])
                   for i,(old,new) in enumerate(zip(before['cards'],after['cards'])) if i!=card['index']):
                raise RuntimeError('未操作的任务发生变化，不能报告单项降级通过')
            self.report.update(result='lower-change-confirmed',boardAfter=after)
            return self.report
        except BaseException as error:
            self.report.update(result='failed',error=str(error));raise
        finally:self.save('last',self.report)
