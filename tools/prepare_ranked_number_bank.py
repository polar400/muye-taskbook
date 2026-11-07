"""Build traceable digit variants from manually labelled saved screenshots. No game IO."""
from pathlib import Path
from functools import lru_cache
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'vendor'))
from adapters.local_ocr import LocalOCR
from PIL import Image,ImageDraw
import numpy as np
from ranked_vision import white_power_templates,white_ink

# Human-checked historical values, never inferred from OCR output. Latest
# 674651/750130 and 960878 failure frames are held out of the variant bank.
SOURCES=[
 ('resources/local/ranked-1920-calibration.png',[672886,1174445,1313308,1419289,1162291]),
 ('resources/local/ranked-power340470-1920.png',[547461,1389901,647519,611663,402865]),
 ('resources/local/catalog/ranked/20261016-973-cross-ready/game.png',[1312030,1698132,1645952,1579496,866320]),
 ('出错任务/排位战/证据/45706e4f3dec2230d7449180.png',[1155227,752120,1066599,618173,769353]),
]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric_box(image,button):
    x,y,w,h=button['box'];cx=round(x+w/2)
    box=[cx-18,y-40,cx+100,y-7]
    patch=image[box[1]:box[3],box[0]:box[2]]
    ys,xs=np.where(white_ink(patch,205))
    assert len(xs)
    return [box[0]+int(xs.min()),box[1]+int(ys.min()),box[0]+int(xs.max())+1,box[1]+int(ys.max())+1]


def align(mask,text):
    """Supervised cut alignment, with the known digit string as the constraint."""
    height,width=mask.shape;bank=dict(white_power_templates())
    paths={(0,0):(0.,[])}
    for x in range(width):
        for i in range(len(text)):
            if (x,i) not in paths:continue
            cost,edges=paths[x,i]
            if not mask[:,x].any():
                end=x
                while end<width and not mask[:,end].any():end+=1
                if end-x<=3 and ((end,i) not in paths or cost<paths[end,i][0]):paths[end,i]=(cost,edges)
                continue
            template=bank[text[i]]
            expected=template.shape[1]*height/template.shape[0]
            for w in range(max(3,round(expected)-2),round(expected)+3):
                end=x+w
                if end>width:continue
                t=np.array(Image.fromarray(template).resize((w,height),Image.Resampling.NEAREST))
                part=mask[:,x:end]
                score=np.count_nonzero(part&t)/max(1,np.count_nonzero(part|t))
                current=(cost+1-score,edges+[(x,end,float(score))])
                if (end,i+1) not in paths or current[0]<paths[end,i+1][0]:paths[end,i+1]=current
    assert (width,len(text)) in paths,text
    return paths[width,len(text)][1]


def main():
    folder=ROOT/'resources/local/ranked_numbers';folder.mkdir(exist_ok=True)
    ocr=LocalOCR();sources=[];templates=[];annotations=[];seen=set();crops=[]
    for source_id,(name,values) in enumerate(SOURCES):
        path=ROOT/name
        with Image.open(path) as im:rgb=np.array(im.convert('RGB'))
        sources.append({'id':source_id,'path':name,'sha256':digest(path)})
        words=ocr.read(rgb[:,:,::-1].copy())
        buttons=sorted([i for i in words if i['text']=='挑战' and i['box'][1]>550],key=lambda i:i['box'][0])
        assert len(buttons)==5
        for button,value in zip(buttons,values):
            box=numeric_box(rgb,button);x,y,r,b=box;region=rgb[y:b,x:r]
            assert b-y==13,(name,box)
            spans=align(white_ink(region,190),str(value));glyphs=[]
            for digit,(left,right,score) in zip(str(value),spans):
                crop=region[:,left:right];mask=white_ink(crop,190)
                key=(digit,mask.shape,mask.tobytes())
                glyph_box=[x+left,y,x+right,b]
                glyphs.append({'digit':digit,'box':glyph_box,'alignmentIoU':score})
                if key in seen:continue
                seen.add(key)
                templates.append({'digit':digit,'sourceId':source_id,'box':glyph_box,
                                  'pixelSha256':hashlib.sha256(crop.tobytes()).hexdigest()})
                crops.append((digit,Image.fromarray(crop)))
            annotations.append({'sourceId':source_id,'value':value,'buttonBox':button['box'],'numericBox':box,'glyphs':glyphs})
    # Retain the existing hand-cropped font exemplars too, especially the
    # complete serif on 1 beside another 1. References remain in the old source.
    cat=ROOT/'resources/local/catalog'
    index=json.loads((cat/'digits/index.json').read_text(encoding='utf-8'))
    family=next(f for f in index['families'] if f['id']=='white_serif_small')
    with Image.open(ROOT/SOURCES[2][0]) as im:
        for digit,ref in family['digits'].items():
            manifest=json.loads((cat/ref['manifest']).read_text(encoding='utf-8'))
            asset=next(a for a in manifest['assets'] if a['id']==ref['assetId'])
            x,y,r,b=asset['box'];box=[x,y+1,r,b-1]
            crop=np.array(im.crop(box).convert('RGB'));mask=white_ink(crop,190)
            key=(digit,mask.shape,mask.tobytes())
            if key in seen:continue
            seen.add(key)
            templates.append({'digit':digit,'sourceId':2,'box':box,
                              'pixelSha256':hashlib.sha256(crop.tobytes()).hexdigest()})
            crops.append((digit,Image.fromarray(crop)))
    counts={d:sum(t['digit']==d for t in templates) for d in '0123456789'}
    assert min(counts.values())>=2,counts
    manifest={'version':1,'family':'ranked_white_small','gameInput':False,
              'sources':sources,'templates':templates,'annotations':annotations,
              'variantCounts':counts,'notes':['Manually labelled source values; supervised cuts reviewed in contact sheet.',
              'Only source pixel references are stored; no duplicate digit PNGs.',
              'Latest 674651/750130 and 960878 screenshots are excluded from the bank.']}
    (folder/'bank.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # An audit sheet is evidence, not a runtime template.
    sheet=Image.new('RGB',(1000,10*130),'#222222');draw=ImageDraw.Draw(sheet)
    for row,digit in enumerate('0123456789'):
        draw.text((5,row*130+5),digit,fill='white')
        for col,(_,crop) in enumerate([c for c in crops if c[0]==digit]):
            if col>=20:break
            enlarged=crop.resize((crop.width*4,crop.height*4),Image.Resampling.NEAREST)
            sheet.paste(enlarged,(35+col*48,row*130+27))
    output=ROOT/'verification/ranked-number-variant-contact-20261019.png';sheet.save(output)
    print(json.dumps({'templates':len(templates),'counts':counts,'sheet':str(output)},ensure_ascii=False))


if __name__=='__main__':main()
