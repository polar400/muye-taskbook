"""Read-only OCR diagnostics for the saved ranked screen; no game input."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np
import json

image=np.array(Image.open(ROOT/'resources/local/ranked-1920-calibration.png').convert('RGB'))[:,:,::-1].copy()
ocr=LocalOCR()
result={'full':ocr.read(image)}
result['opponents']=[]
for item in result['full']:
    if '战斗力' not in item['text'] or item['box'][1]<image.shape[0]*.55:continue
    x,y,w,h=item['box'];region=image[y-3:y+h+3,x-3:x+w+3]
    samples=[]
    for scale in (2,3):
        enlarged=np.array(Image.fromarray(region).resize((region.shape[1]*scale,region.shape[0]*scale)))
        samples.append(ocr.read(enlarged))
    rgb=region[:,:,::-1].astype('float32')
    white=(np.min(rgb,axis=2)>205)&((np.max(rgb,axis=2)-np.min(rgb,axis=2))<35)
    yy,xx=np.where(white)
    digits=np.repeat(np.where(white[yy.min():yy.max()+1,xx.min():xx.max()+1],0,255).astype('uint8')[:,:,None],3,axis=2)
    values=[]
    for stretch in (1,1.5):
        padded=Image.new('RGB',(digits.shape[1]+12,digits.shape[0]+10),'white');padded.paste(Image.fromarray(digits),(6,5))
        resized=padded.resize((padded.width*3,int(padded.height*3*stretch)))
        values.append(ocr.read(np.array(resized),only_rec=True))
    result['opponents'].append({'original':item,'local':samples,'masked':values})
crop=image[85:142,172:382].copy()
rgb=crop[:,:,::-1]
red=(rgb[:,:,0]>140)&(rgb[:,:,0]>rgb[:,:,1]*1.5)&(rgb[:,:,0]>rgb[:,:,2]*1.5)
mask=np.repeat(np.where(red,0,255).astype('uint8')[:,:,None],3,axis=2)
for name,region in [('original',crop),('red_mask',mask)]:
    resized=np.array(Image.fromarray(region).resize((region.shape[1]*3,region.shape[0]*3)))
    result[name]=ocr.read(resized)
    result[name+'_recognition']=ocr.read(resized,only_rec=True)
    Image.fromarray(resized[:,:,::-1]).save(ROOT/'verification'/('ranked-'+name+'.png'))
ys,xs=np.where(red)
tight=mask[ys.min():ys.max()+1,xs.min():xs.max()+1]
for stretch in (1,1.5,2,2.5):
    padded=Image.new('RGB',(tight.shape[1]+16,tight.shape[0]+12),'white')
    padded.paste(Image.fromarray(tight),(8,6))
    scaled=padded.resize((padded.width*3,int(padded.height*3*stretch)))
    result['stretch_'+str(stretch)]=ocr.read(np.array(scaled),only_rec=True)
    scaled.save(ROOT/'verification'/('ranked-stretch-'+str(stretch)+'.png'))
present=np.any(red,axis=0)
groups=[];start=None
for index,value in enumerate([*present,False]):
    if value and start is None:start=index
    if not value and start is not None:groups.append((start,index));start=None
result['glyphs']=[]
for left,right in groups:
    pixels=red[:,left:right]
    yy,xx=np.where(pixels)
    glyph=mask[yy.min():yy.max()+1,left:right]
    padded=Image.new('RGB',(glyph.shape[1]+12,glyph.shape[0]+12),'white')
    padded.paste(Image.fromarray(glyph),(6,6))
    result['glyphs'].append({'range':[left,right],'ocr':ocr.read(np.array(padded.resize((padded.width*4,padded.height*4))),only_rec=True)})
for shear in (.2,.4,.6):
    base=Image.fromarray(tight)
    aligned=base.transform((base.width+base.height,base.height),Image.Transform.AFFINE,(1,-shear,0,0,1,0),fillcolor='white')
    padded=Image.new('RGB',(aligned.width+16,aligned.height+12),'white');padded.paste(aligned,(8,6))
    for stretch in (1,2):
        scaled=padded.resize((padded.width*3,padded.height*3*stretch))
        result[f'shear_{shear}_{stretch}']=ocr.read(np.array(scaled),only_rec=True)
(ROOT/'verification/ranked-ocr-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
