"""Arena task-card templates from original pixels; never operate the game."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'resources/local/arena_daily/image'


def main():
    DEST.mkdir(parents=True,exist_ok=True);records=[]
    refs='resources/local/arena/references/'
    assets=[
        ('eligible','resources/local/catalog/arena/20261016-973-team-ready/condition_met.png',None),
        ('unmet',refs+'reward-unmet-user.png',(119,424,220,453)),
        ('claim',refs+'reward-ready-user.png',(137,373,235,409)),
        ('lower',refs+'lower-difficulty-user.png',(107,13,206,52)),
        ('lower_highlight','verification/arena-hover-live-20261020-000058-120721/physical-after-1.png',(220,485,319,524)),
        ('progress_zero','resources/local/catalog/arena/20261016-973-team-ready/game.png',(224,530,320,553)),
        ('progress_zero_unmet',refs+'reward-unmet-user.png',(120,460,219,486)),
        ('progress_zero_lower',refs+'lower-difficulty-user.png',(107,57,208,83)),
        ('progress_done',refs+'reward-ready-user.png',(139,415,237,439)),
        ('header','resources/local/arena/task_header.png',None)]
    for name,source,box in assets:
        image=Image.open(ROOT/source).convert('RGB')
        if box:image=image.crop(box)
        path=DEST/(name+'.png');image.save(path)
        records.append(dict(name=name,source=source,box=box,path=path.relative_to(ROOT).as_posix(),
                            sourceSha256=hashlib.sha256((ROOT/source).read_bytes()).hexdigest(),
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (DEST.parent/'sources.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(len(records),'original-pixel arena task templates')


if __name__=='__main__':main()
