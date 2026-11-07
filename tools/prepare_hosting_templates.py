"""Crop the user's calibrated 1920 x 1015 hosting entrance fixture."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'vendor'))
from PIL import Image


def main():
    source = ROOT/'resources/local/hosting-1920-calibration.png'
    image = Image.open(source).convert('RGB')
    if image.size != (1920, 1015):
        raise RuntimeError('托管标定截图必须为 1920 x 1015')
    # Orange monitor below the right side of the 中忍勋章 badge.
    target = ROOT/'resources/local/image/computer_1920_verified.png'
    image.crop((670, 129, 706, 163)).save(target)
    print(target)
    confirmation = Image.open(ROOT/'resources/local/hosting-first-confirm-1920.png').convert('RGB')
    if confirmation.size != (1920, 1015):
        raise RuntimeError('首次托管确认截图必须为 1920 x 1015')
    card = ROOT/'resources/local/image/hosting_card1_1920_verified.png'
    confirmation.crop((800, 475, 887, 498)).save(card)
    print(card)


if __name__ == '__main__':
    main()
