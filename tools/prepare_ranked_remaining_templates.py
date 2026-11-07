"""Extract the visually verified red 4 from the archived remaining-six frame."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ranked_vision import split_glyphs
from PIL import Image
import numpy as np

image=np.array(Image.open(ROOT/'resources/local/ranked-remaining6-1920.png').convert('RGB'))
if image.shape[:2]!=(1015,1920):raise RuntimeError('排位战样本必须为1920×1015')
height,width=image.shape[:2]
region=image[int(height*.084):int(height*.145),int(width*.09):int(width*.27)].astype('float32')
r,g,b=(region[:,:,i] for i in range(3))
glyphs=split_glyphs((r>140)&(r>g*1.5)&(r>b*1.5))
if len(glyphs)!=6:raise RuntimeError('已核对的565140字形数量不一致')
target=ROOT/'resources/local/image/ranked_power_digit4_remaining6.png'
Image.fromarray(np.where(glyphs[4],0,255).astype('uint8')).save(target)
print(target)
