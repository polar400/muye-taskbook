"""Preserve user screenshots and crop arena popup anchors without rescaling."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'resources/local/arena/popups'
REFS=ROOT/'resources/local/arena_popup_references'
GAME_CROP=(45,127,1965,1142)


def preserve_battle_confirmation(source):
    """Regression reference only; the shared victory art already recognizes it."""
    REFS.mkdir(parents=True,exist_ok=True);source=Path(source)
    original=REFS/'battle-victory-confirm-user.png';shutil.copyfile(source,original)
    image=Image.open(original).convert('RGB')
    if image.size!=(2010,1191):raise RuntimeError('战斗确认原图尺寸变化，需重新核对游戏区')
    crop=(45,130,1965,1145);game=REFS/'battle-victory-confirm-game.png';image.crop(crop).save(game)
    (REFS/'battle-victory-confirm-20261025.json').write_text(json.dumps(dict(
        source=original.relative_to(ROOT).as_posix(),originalFilename=source.name,
        sourceSha256=hashlib.sha256(original.read_bytes()).hexdigest(),gameCrop=crop,
        game=game.relative_to(ROOT).as_posix(),gameSha256=hashlib.sha256(game.read_bytes()).hexdigest(),
        size=[1920,1015],runtimeTemplate=False,buttonText='确认'),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Battle blue-confirm source preserved without adding runtime templates')


def prepare(trial,victory):
    DEST.mkdir(parents=True,exist_ok=True);REFS.mkdir(parents=True,exist_ok=True)
    records=[];references=[]
    for name,source,templates in (
        ('trial',Path(trial),{'trial_title':(735,135,1190,235),'trial_skip':(1135,696,1256,737)}),
        ('victory',Path(victory),{'victory_title':(755,135,1155,235),'victory_confirm':(846,714,1040,765)})):
        original=REFS/(name+'-user.png');shutil.copyfile(source,original)
        image=Image.open(original).convert('RGB')
        if image.size!=(2010,1188):raise RuntimeError('用户原图尺寸变化，需重新核对游戏区域')
        game=image.crop(GAME_CROP);game_path=REFS/(name+'-game.png');game.save(game_path)
        references.append(dict(kind=name,path=original.relative_to(ROOT).as_posix(),
            sha256=hashlib.sha256(original.read_bytes()).hexdigest(),originalFilename=source.name,
            game=game_path.relative_to(ROOT).as_posix(),gameCrop=GAME_CROP,
            gameSha256=hashlib.sha256(game_path.read_bytes()).hexdigest()))
        for key,box in templates.items():
            path=DEST/(key+'.png');game.crop(box).save(path)
            records.append(dict(name=key,path=path.relative_to(ROOT).as_posix(),
                source=game_path.relative_to(ROOT).as_posix(),box=box,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),sourceSha256=hashlib.sha256(game_path.read_bytes()).hexdigest()))
    (DEST/'sources.json').write_text(json.dumps(dict(size=[1920,1015],threshold=.9,
        references=references,assets=records),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Two original screenshots retained; four original-pixel arena popup anchors prepared')


if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('Usage: prepare_arena_popup_assets.py TRIAL VICTORY')
    if sys.argv[1]=='--battle-confirm':preserve_battle_confirmation(sys.argv[2])
    else:prepare(*sys.argv[1:])
