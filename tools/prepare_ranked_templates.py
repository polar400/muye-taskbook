"""Extract manually verified red power glyphs from the two supplied ranked frames."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image
import numpy as np

def glyphs(image):
    crop=np.array(image.convert('RGB'))
    r,g,b=(crop[:,:,index].astype('float32') for index in range(3))
    red=(r>140)&(r>g*1.5)&(r>b*1.5)
    groups=[];start=None
    for x,occupied in enumerate([*np.any(red,axis=0),False]):
        if occupied and start is None:start=x
        if not occupied and start is not None:
            ys,_=np.where(red[:,start:x]);groups.append(red[ys.min():ys.max()+1,start:x]);start=None
    return groups

frames=[(ROOT/'resources/local/ranked-1920-calibration.png',(172,85,382,142),'565120','runtime'),
        (Path('C:/Users/lenovo/AppData/Local/Temp/codex-clipboard-d57a94ae-a599-468c-b591-2866155c0d0e.png'),(172,192,382,249),'565120','user')]
for path,box,number,source in frames:
    values=glyphs(Image.open(path).crop(box))
    if len(values)!=len(number):raise RuntimeError('Glyph count changed: '+str(path))
    for value,digit in zip(values,number):
        Image.fromarray(np.where(value,0,255).astype('uint8')).save(ROOT/'resources/local/image'/f'ranked_power_digit{digit}_{source}.png')
