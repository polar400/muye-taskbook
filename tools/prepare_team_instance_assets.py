"""Preserve user references and derive team-instance-only navigation templates."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'resources/local/team_instance'
SOURCES = {
    'kunai': 'd09b9940-8ee0-4089-b207-70d8b1384426',
    'activities': '10e5c18f-6ee3-4409-9500-0085b440483f',
    'row': '22d9e06a-7e3a-4c8a-a3fd-a6e474fb3fee',
    'participate': 'f67d57c1-b2fc-4a98-8a99-b97384c4a036',
}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    for name, identifier in SOURCES.items():
        source = Path('C:/Users/lenovo/AppData/Local/Temp') / ('codex-clipboard-' + identifier + '.png')
        data = source.read_bytes()
        (OUT / (name + '-source.png')).write_bytes(data)
        records[name] = {'source': str(source), 'sha256': hashlib.sha256(data).hexdigest()}
    game = Image.open(OUT / 'activities-source.png').crop((45, 151, 1965, 1166))
    game.save(OUT / 'activities-game.png')
    crops = {'limited_active': (496, 51, 692, 121),
             'team_row_blue': (303, 286, 448, 337),
             'participate': (1270, 682, 1408, 723)}
    for name, box in crops.items():
        game.crop(box).save(OUT / (name + '.png'))
    Image.open(OUT / 'kunai-source.png').save(OUT / 'kunai.png')
    Image.open(OUT / 'row-source.png').crop((44, 22, 185, 73)).save(OUT / 'team_row_plain.png')
    records['derived'] = {'gameCrop': [45,151,1965,1166], 'gameCrops': crops,
                          'plainRowCrop': [44,22,185,73]}
    (OUT / 'sources.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
