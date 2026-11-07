"""Extract only visually verified ranked red 7/8 variants. No game IO."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)];sys.path.insert(0,str(ROOT/'vendor'))
from ranked_vision import split_glyphs
from PIL import Image
import numpy as np

SOURCES=['verification/failure-20261106-005541-308d39bb9a19-ranked.png',
         'verification/failure-20261106-005612-02e7419ac0d1-ranked.png']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(path):
    rgb=np.array(Image.open(path).convert('RGB'))
    if rgb.shape!=(1015,1920,3):raise RuntimeError('source is not calibrated 1920x1015')
    h,w=rgb.shape[:2];left,top=int(w*.09),int(h*.084)
    region=rgb[top:int(h*.145),left:int(w*.27)].astype('float32')
    r,g,b=region.transpose(2,0,1);mask=(r>140)&(r>g*1.5)&(r>b*1.5)
    glyphs=split_glyphs(mask)
    if len(glyphs)!=6:raise RuntimeError('verified 571238 source does not contain six glyphs')
    boxes=[];start=None
    for x,occupied in enumerate([*np.any(mask,axis=0),False]):
        if occupied and start is None:start=x
        if not occupied and start is not None:
            ys,_=np.where(mask[:,start:x])
            boxes.append([left+start,top+int(ys.min()),left+x,top+int(ys.max())+1]);start=None
    return glyphs,boxes


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-root',type=Path,default=ROOT)
    output=parser.parse_args().output_root
    extracted=[extract(ROOT/name) for name in SOURCES]
    rows=[]
    # Labels are manually checked source annotations, never a runtime power.
    for index,digit in ((1,'7'),(5,'8')):
        glyph=extracted[0][0][index]
        if any(not np.array_equal(glyph,other[0][index]) for other in extracted[1:]):
            raise RuntimeError('the two archived observations disagree on glyph pixels')
        pixels=np.where(glyph,0,255).astype('uint8')
        name=f'resources/local/image/ranked_power_digit{digit}_failure571238_{index}.png'
        path=output/name
        if path.exists():
            if not np.array_equal(np.array(Image.open(path).convert('L')),pixels):
                raise RuntimeError('existing template differs; refusing overwrite: '+str(path))
        else:
            path.parent.mkdir(parents=True,exist_ok=True);Image.fromarray(pixels).save(path)
        rows.append(dict(digit=digit,glyphIndex=index,path=name,sha256=digest(path),
                         pixelSha256=hashlib.sha256(pixels.tobytes()).hexdigest(),
                         shape=list(pixels.shape),sourceBoxes=[result[1][index] for result in extracted]))
    manifest=dict(version=1,annotation='571238',actualGameInputs=0,
                  sources=[dict(path=name,sha256=digest(ROOT/name)) for name in SOURCES],
                  templates=rows,notes=['Both observations have identical new glyph pixels; not independent font holdouts.',
                                       'Only 7 and 8 are added; existing reader thresholds and all old templates retained.'])
    path=output/'resources/local/ranked-red571238-sources.json';path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    if path.exists() and path.read_text(encoding='utf-8')!=content:raise RuntimeError('existing source manifest differs')
    path.write_text(content,encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
