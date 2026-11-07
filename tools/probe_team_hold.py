"""One authorized list-only trial; no dungeon or confirmation clicks."""
import sys,json,ctypes
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from team_instance_task import TeamInstanceTask
from team_instance_challenge import Challenge,LEVELS

def main():
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    folder=ROOT/'verification'/('team-hold-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    folder.mkdir()
    report={'inputs':[],'result':'failed'}
    try:
        windows=game_windows();report['windows']=windows
        if len(windows)!=1:raise RuntimeError('没有唯一游戏窗口；零输入')
        actual=BackgroundWindow(windows[0][0]);actual.calibrate()
        class Window:
            index=0
            def capture(self):return actual.capture()
            def save(self,image,path):
                actual.save(image,folder/f'frame-{self.index}.png');self.index+=1
            def click(self,x,y):
                report['inputs'].append(dict(type='tab',x=x,y=y));actual.click(x,y)
            def hold(self,x,y,seconds,cancelled):
                report['inputs'].append(dict(type='hold',x=x,y=y,seconds=seconds))
                return actual.hold(x,y,seconds,cancelled)
        flow=LocalFlows(Window(),LocalOCR(),{},lambda:None,lambda *a,**k:None)
        task=TeamInstanceTask(flow);c=Challenge(task);flow.observe()
        if not c.panel():raise RuntimeError('请停在副本列表；未导航或挑战')
        if not c.all_tab():task.click('全部副本',lambda:c.match(['all_inactive','all_inactive_live']) if c.panel() else None)
        task.wait(c.all_tab)
        for index in range(3):
            if c.target(LEVELS[-1]):break
            c.hold_scroll('down',index)
        report['bottomVerified']=bool(c.target(LEVELS[-1]))
        report['result']='bottom_verified' if report['bottomVerified'] else 'three_holds_unverified'
    except Exception as e:report['error']=str(e)
    finally:
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(folder);print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
