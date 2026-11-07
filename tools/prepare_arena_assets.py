"""Prepare home-icon arena entry; retain retired navigation and reward evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'resources/local/arena'


def prepare(home_icon,home_tray,reward_ready,reward_unmet):
    DEST.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((DEST/'sources.json').read_text(encoding='utf-8'))
    records=[r for r in manifest['assets'] if not r['name'].startswith('home_entry_')]
    active={'ranked_battle','casual_battle','score_label','task_header'}
    for record in records:
        record['runtimeEnabled']=record['name'] in active
        if not record['runtimeEnabled']:record['retiredReason']='入口改为主界面竞技场图标；旧素材保留，不再调用'
    refs=DEST/'references';refs.mkdir(exist_ok=True)
    references=[]
    for name,source,state in (
        ('home-icon-user',home_icon,'主界面竞技场独立图标'),
        ('home-tray-user',home_tray,'主界面图标组，含竞技场及相邻图标'),
        ('reward-ready-user',reward_ready,'两项任意阵容胜利任务1/1，各250，显示领取按钮'),
        ('reward-unmet-user',reward_unmet,'剩余4项；风属性奥义伤害与中毒忍者任务0/1，各500，条件未满足')):
        target=refs/(name+'.png');shutil.copyfile(source,target)
        references.append(dict(path=target.relative_to(ROOT).as_posix(),
                               originalFilename=Path(source).name,state=state,
                               sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                               size=list(Image.open(target).size),runtimeEnabled=False))
    def asset(name,source,box):
        source=Path(source)
        target=DEST/(name+'.png')
        Image.open(source).convert('RGB').crop(box).save(target)
        records.append(dict(name=name,path=target.relative_to(ROOT).as_posix(),
                            source=source.relative_to(ROOT).as_posix(),box=box,runtimeEnabled=True,
                            sourceSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    # Stadium art only: exclude the map background, outer glow and label.
    asset('home_entry_catalog',ROOT/'resources/local/catalog/home/20261013-974-village/arena.png',(14,25,70,74))
    asset('home_entry_user',refs/'home-icon-user.png',(16,15,69,61))
    manifest.update(route='home-icon',assets=records,references=references,
                    rewardAutomationEnabled=False)
    (DEST/'sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('6 active templates; 7 retired navigation templates retained; 4 references saved')


if __name__=='__main__':
    if len(sys.argv)!=5:raise SystemExit('Usage: prepare_arena_assets.py HOME_ICON HOME_TRAY REWARD_READY REWARD_UNMET')
    prepare(*(Path(p) for p in sys.argv[1:]))
