"""Prepare only the calibrated ranked end-battle button artwork."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image


def main():
    image=Image.open(ROOT/'resources/local/ranked-battle-1920.png').convert('RGB')
    if image.size!=(1920,1015):
        raise RuntimeError('排位战战斗样本必须为1920×1015')
    target=ROOT/'resources/local/image/end_battle_1920_verified.png'
    # Star and vertical 结束战斗 artwork; excludes the retreat button to its right.
    image.crop((1668,902,1795,1005)).save(target)
    print(target)


if __name__=='__main__':main()
