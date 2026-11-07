"""Rebuild fixed strong-panel assets from the supplied 1920x1015 fixture."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image

image=Image.open(ROOT/'resources/local/strong-1920-calibration.png').convert('RGB')
for name,box in {
    'strong_enter':(614,642,856,715),
    'strong_count1':(890,911,913,941),
    'strong_count0':(1294,911,1322,941),
}.items():
    image.crop(box).save(ROOT/'resources/local/image'/f'{name}_1920_verified.png')
