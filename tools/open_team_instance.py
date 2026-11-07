"""Independent team-instance entry. Default lists windows; --open navigates once."""
import argparse
import ctypes
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from app import game_windows
from adapters.background_window import BackgroundWindow
from adapters.local_ocr import LocalOCR
from local_flows import LocalFlows
from team_instance_task import run_team_instance

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--hwnd', type=int)
    parser.add_argument('--challenge-once',action='store_true')
    args = parser.parse_args()
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    windows = game_windows()
    print(json.dumps(windows,ensure_ascii=False),flush=True)
    if not args.open:
        return 0
    if args.hwnd is not None:
        windows = [w for w in windows if w[0]==args.hwnd]
    if len(windows)!=1:
        raise RuntimeError('无法唯一连接游戏窗口；未发送输入')
    folder = ROOT/'verification'/('team-instance-live-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir()
    report = dict(result='failed', openedVerified=False, inputs=[], events=[])
    def save():
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def emit(kind,message,**extra):
        report['events'].append(dict(kind=kind,message=message,**extra))
        print(message,flush=True)
    class Window:
        def __init__(self):
            self.actual = BackgroundWindow(windows[0][0])
            self.index = 0
        def capture(self):
            return self.actual.capture()
        def save(self,image,path):
            self.actual.save(image,folder/f'frame-{self.index:03d}.png')
            self.index += 1
        def click(self,x,y):
            item = dict(x=x,y=y,status='sending')
            report['inputs'].append(item)
            save()
            self.actual.click(x,y)
            item['status']='sent'
            save()
        def hold(self,x,y,seconds,cancelled=lambda:False):
            item=dict(type='hold',x=x,y=y,seconds=seconds,status='sending')
            report['inputs'].append(item)
            save()
            try:
                result=self.actual.hold(x,y,seconds,cancelled)
                item['status']='released' if result else 'cancelled_released'
                return result
            finally:save()
    try:
        window = Window()
        window.save(window.actual.calibrate(log=lambda m:emit('log',m)),None)
        cfg={'tasks':['team_instance']}
        if args.challenge_once:cfg.update(teamInstanceName='桥上的决战',teamInstanceDifficulty='简单')
        flow = LocalFlows(window,LocalOCR(),cfg,lambda:None,emit)
        report['result'] = run_team_instance(flow)
        return 2  # Navigation sent, destination is still unverified.
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        save()
        print('Evidence:',folder,flush=True)

if __name__=='__main__':
    sys.exit(main())
