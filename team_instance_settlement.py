"""Team-only reward selection and verified return; no repeated challenges."""
import random

class Settlement:
    def __init__(self,task):self.t=task;self.f=task.f

    def title(self):
        return self.t.template(['settlement_title'],(500,0,1400,230))

    def row(self,index):
        title=self.title()
        if not title:return None
        x,y,_,_=title['box'];cards=[]
        for column in range(5):
            left=x-270+204*column;top=y+165+410*index
            roi=(left-8,top-8,left+192,top+263)
            picked=self.t.template(['card_selected'],roi)
            back=self.t.template(['card_back'],roi)
            cards.append(dict(picked=bool(picked),back=bool(back),box=[left+40,top+65,100,120]))
        selected=[i for i,c in enumerate(cards) if c['picked']]
        if len(selected)>1:raise RuntimeError('结算同排选中牌不唯一')
        if selected:return dict(selected=selected[0],cards=cards)
        return dict(selected=None,cards=cards) if all(c['back'] for c in cards) else None

    def home(self):
        return self.t.home_visible()

    def run(self):
        self.t.wait(self.title)
        for row in range(2):
            state=self.t.wait(lambda:self.row(row))
            if state['selected'] is not None:continue
            chosen=random.randrange(5)
            def target():
                current=self.row(row)
                return current['cards'][chosen] if current and current['selected'] is None else None
            self.t.click('结算翻牌'+str(row),target)
            self.t.wait(lambda:(state:=self.row(row)) and state['selected']==chosen)
        self.t.click('返回游戏',lambda:self.t.template(['return_game','return_game_revealed'],(1100,850,1600,990)) if self.title() else None)
        stable=0
        def returned():
            nonlocal stable
            from team_instance_challenge import Challenge
            # Returning may expose the dungeon list. Daily runner closes it
            # after reaching the quota; it is not called the home screen.
            destination='home' if self.home() else 'panel' if not self.title() and Challenge(self.t).panel() else None
            stable=stable+1 if destination and destination==getattr(self,'last_destination',None) else 1 if destination else 0
            self.last_destination=destination
            return stable>=2
        self.t.wait(returned)
        return 'completed'

def finish_challenge(task):
    settlement=Settlement(task)
    task.f.observe()
    if not settlement.title():
        task.f.auto()  # Existing common auto + x2 implementation, unchanged.
    old=task.timeout
    try:
        task.timeout=task.f.cfg.get('battleSeconds',900)
        task.wait(settlement.title)
    finally:task.timeout=old
    return settlement.run()
