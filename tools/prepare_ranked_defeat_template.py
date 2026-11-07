"""Extract the explicit defeat artwork from a visually verified settlement."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image


def main():
    image=Image.open(ROOT/'resources/local/ranked-defeat-1920.png').convert('RGB')
    if image.size!=(1920,1015):
        raise RuntimeError('排位战结算样本必须为1920×1015')
    # Only the decorative 败 character and its immediate background; excludes
    # the statistics/confirmation buttons and the health bars. Runtime matches
    # within the central result region, never clicks these sample coordinates.
    target=ROOT/'resources/local/image/defeat_1920_verified.png'
    image.crop((805,305,1145,607)).save(target)
    print(target.name)


if __name__=='__main__':main()
