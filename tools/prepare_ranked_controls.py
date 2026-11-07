"""Prepare scope and free refresh artwork from preserved user samples."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image


def main():
    image=Image.open(ROOT/'resources/local/ranked-remaining6-live.png').convert('RGB')
    targets={
        'ranked_local':(1592,10,1637,64),
        'ranked_cross':(1698,10,1743,64),
        'ranked_title_cross':(755,12,806,131),
        'ranked_refresh':(1661,889,1783,935),
    }
    for name,box in targets.items():
        image.crop(box).save(ROOT/f'resources/local/image/{name}_1920_verified.png')
    local=Image.open(ROOT/'resources/local/ranked-local-live.png').convert('RGB')
    local.crop((755,12,806,131)).save(ROOT/'resources/local/image/ranked_title_local_1920_verified.png')
    local.crop(targets['ranked_local']).save(ROOT/'resources/local/image/ranked_local_selected.png')
    local.crop(targets['ranked_cross']).save(ROOT/'resources/local/image/ranked_cross_unselected.png')


if __name__=='__main__':main()
