"""Extract three manually verified glyph variants from the classified sample.

The source's 341307 is a verified annotation, not runtime power configuration.
Only missing variants are added; the user's catalog and older templates stay intact.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from ranked_vision import split_glyphs
from PIL import Image
import numpy as np

sample=ROOT/'resources/local/catalog/ranked/20261013-974-cross-ready/game.png'
image=np.array(Image.open(sample).convert('RGB'))
if image.shape[:2]!=(1015,1920):raise RuntimeError('排位战样本必须为1920×1015')
height,width=image.shape[:2]
region=image[int(height*.084):int(height*.145),int(width*.09):int(width*.27)].astype('float32')
r,g,b=(region[:,:,i] for i in range(3))
glyphs=split_glyphs((r>140)&(r>g*1.5)&(r>b*1.5))
if len(glyphs)!=6:raise RuntimeError('已核对的341307字形数量不一致')
for index in (2,3,5):
    digit='341307'[index]
    target=ROOT/'resources/local/image'/f'ranked_power_digit{digit}_catalog341307_{index}.png'
    Image.fromarray(np.where(glyphs[index],0,255).astype('uint8')).save(target)
    print(target.name)
