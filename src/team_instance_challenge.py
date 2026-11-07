"""Single selected dungeon entry; all input targets derive from current pixels."""
LEVELS=('桥上的决战','追击我爱罗','音之九人众','上忍试炼','晓组织降临','蛇之重生','痛苦轮回','兄弟诀别','五影会谈')
DIFFICULTIES=('简单','普通','困难')
TEMPLATES={'简单':'difficulty_easy','普通':'difficulty_normal','困难':'difficulty_hard'}

class Challenge:
    def __init__(self,task):
        self.t=task
        self.f=task.f

    def match(self,names,roi=(0,0,1920,1015)):
        return self.t.template(names,roi)

    def panel(self):
        return bool(not self.t.blocked() and self.match(['reward_label']) and self.match(['all_active','all_inactive','all_inactive_live']))

    def all_tab(self):
        return self.match(['all_active']) if self.panel() else None

    def cards(self):
        tab=self.all_tab()
        if not tab:return None
        x,y,_,_=tab['box']
        left=x-155;top=y+45
        cards=[]
        for dy in (0,320):
            for dx in (0,600):
                roi=(max(0,left+dx),max(0,top+dy),min(1920,left+dx+660),min(1015,top+dy+320))
                detail=self.match(['details_button'],roi)
                if detail:cards.append(detail)
        return cards

    def target(self,name):
        cards=self.cards()
        if not cards:return None
        found=[]
        for card in cards:
            x,y,w,h=card['box']
            roi=(max(0,x-25),max(0,y-290),min(1920,x+570),y)
            title=self.match(['level_'+str(LEVELS.index(name))],roi)
            if title:found.append(card)
        if len(found)>1:raise RuntimeError('同名副本不唯一，停止')
        return found[0] if found else None

    def difficulty(self,card):
        x,y,w,h=card['box']
        roi=(x+240,y-18,min(1920,x+430),min(1015,y+45))
        found=[(name,self.match([template],roi)) for name,template in TEMPLATES.items()]
        found=[p for p in found if p[1]]
        if len(found)!=1:return None
        return found[0]

    def arrow(self,direction):
        return self.match(['scroll_'+direction]) if self.all_tab() else None

    def confirm(self):
        if not self.match(['confirm_warning']):return None
        return self.match(['confirm_enter'])

    def boundary(self):
        """Read the cyan scrollbar thumb only inside the verified all-list."""
        up=self.arrow('up');down=self.arrow('down')
        if not down:return None
        import numpy as np
        if up:x,y,w,h=up['box']
        else:
            # A disabled top arrow has a different appearance. The verified
            # bottom arrow anchors the same 573-pixel track in this layout.
            x,bottom,w,_=down['box'];y=bottom-603;h=30
        bottom=down['box'][1]
        if bottom-y-h<100:return None
        strip=self.f.image[y+h:bottom,x+w//2-4:x+w//2+5].astype('int16')
        blue,green,red=(strip[:,:,i] for i in range(3))
        rows=np.where(((blue>red+40)&(green>red+40)&(blue>80)).mean(axis=1)>.6)[0]
        if len(rows)<50 or rows[-1]-rows[0]+1!=len(rows):return None
        if rows[0]<=30 and rows[-1]<len(strip)-40:return 'top'
        if rows[-1]>=len(strip)-31 and rows[0]>40:return 'bottom'
        return None

    def find_target(self,name):
        for direction in ('up','down'):
            for batch in range(3):
                self.f.observe()
                card=self.target(name)
                if card:return card
                if direction=='up' and (self.boundary()=='top' or self.target(LEVELS[0])):break
                if direction=='down' and (self.boundary()=='bottom' or self.target(LEVELS[-1])):
                    raise RuntimeError('已到底部但目标关卡未识别，停止翻页')
                self.hold_scroll(direction,batch)
        self.f.observe()
        card=self.target(name)
        if not card:raise RuntimeError('三组翻页后未识别目标关卡，停止')
        return card

    def hold_scroll(self,direction,index):
        target=self.t.wait(lambda:self.arrow(direction))
        before=self.f.image[200:820,370:1530].copy()
        x,y,w,h=target['box']
        self.f.checkpoint()
        seconds=.55 if direction=='down' else .35
        self.f.log(f'组队副本：长按翻页{direction}第{index+1}次，{seconds}秒')
        complete=self.f.window.hold(x+w//2,y+h//2,seconds,getattr(self.f,'team_hold_cancelled',lambda:False))
        if not complete:
            self.f.checkpoint()
            raise RuntimeError('长按已取消并释放，请重新识别后运行')
        self.f.observe()
        if not self.all_tab():raise RuntimeError('长按后页面不明，已释放并停止')
        import numpy as np
        if np.abs(self.f.image[200:820,370:1530].astype('int16')-before.astype('int16')).mean()<.5:
            raise RuntimeError('长按后列表未变化，已释放并停止')

    def run(self,name,difficulty):
        self.t.click('全部副本',lambda:self.match(['all_inactive','all_inactive_live']) if self.panel() and not self.all_tab() else self.all_tab())
        self.t.wait(self.all_tab)
        card=self.find_target(name)
        if not card:raise RuntimeError('未找到标题与详情按钮完整的目标副本；停止')
        for step in range(3):
            self.f.observe()
            card=self.target(name)
            current=self.difficulty(card) if card else None
            if current is None:raise RuntimeError('无法核对目标关卡难度')
            if current[0]==difficulty:break
            previous=current[0]
            delta=-1 if DIFFICULTIES.index(previous)>DIFFICULTIES.index(difficulty) else 1
            def difficulty_arrow():
                fresh=self.target(name)
                value=self.difficulty(fresh) if fresh else None
                if not value or value[0]!=previous:return None
                x,y,w,h=value[1]['box']
                return dict(box=[x-37 if delta<0 else x+w+5,y,30,h])
            self.t.click('调整难度'+str(step),difficulty_arrow)
            expected=DIFFICULTIES[DIFFICULTIES.index(previous)+delta]
            def changed():
                fresh=self.target(name)
                value=self.difficulty(fresh) if fresh else None
                return value if value and value[0]==expected else None
            self.t.wait(changed)
        else:raise RuntimeError('难度调整未完成')
        def enter():
            fresh=self.target(name)
            value=self.difficulty(fresh) if fresh else None
            if not value or value[0]!=difficulty:return None
            x,y,_,_=fresh['box']
            return dict(box=[x+220,y-140,80,60])
        self.t.click('进入所选关卡',enter)
        self.t.click('确认进入挑战',self.confirm)
        self.f.observe()
        self.f.log('已确认进入：'+name+'／'+difficulty+'；检查自动及二倍速，等待结算')
        from team_instance_settlement import finish_challenge
        return finish_challenge(self.t)
