"""Preserve user references and crop welfare-only templates; no game input."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'resources/local/welfare'
IDS = ['202dc1f3-586c-4add-8610-147beeb4b1c1', '831405ea-48a2-49e3-b61a-5007bc72c3cb',
       'ae3b6835-9d38-4641-a9b8-7bc8dcb3b149', '01ada5c6-b5d2-44e1-995b-8ed4366591b0',
       '4e21cb49-1c43-4b02-a1fb-cc64d6724261', 'd4abc38c-618a-4c31-8274-9dac080b9f98',
       '364ca94d-f070-492a-b313-34779ebb45b6']


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / 'image').mkdir(exist_ok=True)
    records = {}
    images = []
    for i, ident in enumerate(IDS, 1):
        src = Path('C:/Users/lenovo/AppData/Local/Temp') / ('codex-clipboard-' + ident + '.png')
        data = src.read_bytes()
        (DEST / f'reference-{i}.png').write_bytes(data)
        records[f'reference-{i}.png'] = {'source': str(src), 'sha256': hashlib.sha256(data).hexdigest()}
        images.append(Image.open(src))
    crops = {
        'entry': (1, (0, 0, 109, 112)),
        'entry_icon': (1, (25, 19, 85, 83)),
        'entry_label': (1, (17, 85, 98, 106)),
        'close': (3, (1617, 257, 1670, 311)),
        'daily_tab': (7, (443, 483, 557, 522)),
        'online_tab': (3, (440, 392, 562, 433)),
        'daily_selected': (3, (393, 459, 562, 505)),
        'online_selected': (7, (392, 394, 562, 443)),
        'daily_header': (3, (649, 418, 863, 475)),
        'online_header': (7, (1036, 435, 1386, 520)),
        'claim_daily': (3, (1003, 919, 1128, 963)),
        'claim_online': (7, (1002, 892, 1132, 936)),
    }
    for name, (source, box) in crops.items():
        path = DEST / 'image' / (name + '.png')
        images[source-1].crop(box).save(path)
        records['image/'+path.name] = {'reference': f'reference-{source}.png', 'box': box,
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    medal = DEST/'reference-medal-live.png'
    if medal.exists():
        box = (1302, 697, 1427, 741)
        target = DEST/'image/claim_medal.png'
        Image.open(medal).crop(box).save(target)
        records[medal.name] = {'source': 'user attachment codex-clipboard-999c38d5-4843-4593-a394-6bb0992af5f0.png',
                              'sha256': hashlib.sha256(medal.read_bytes()).hexdigest()}
        records['image/claim_medal.png'] = {'reference': medal.name, 'box': box,
                                          'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    live = ROOT/'verification/welfare-20261027-003037-aa948325/037.png'
    if live.exists():
        data = live.read_bytes()
        (DEST/'reference-claimed-live.png').write_bytes(data)
        records['reference-claimed-live.png'] = {'source': str(live.relative_to(ROOT)),
                                               'sha256': hashlib.sha256(data).hexdigest()}
        box = (980, 779, 1057, 805)
        target = DEST/'image/received.png'
        Image.open(live).crop(box).save(target)
        records['image/received.png'] = {'reference': 'reference-claimed-live.png', 'box': box,
                                       'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    (DEST / 'sources.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
