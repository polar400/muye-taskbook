"""Promote verified ranked 9 and a stable end-button label from saved sources."""
from pathlib import Path
from hashlib import sha256
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from ranked_vision import split_glyphs
from PIL import Image
import numpy as np


def digest(p):
    return sha256(p.read_bytes()).hexdigest()


def save_new(image,path):
    if path.exists():
        if not np.array_equal(np.array(Image.open(path)),np.array(image)):
            raise RuntimeError('已有模板与已核对来源不一致，保留原文件：'+str(path))
    else:
        image.save(path)


def main():
    catalog=ROOT/'resources/local/catalog/ranked/20261016-973-cross-ready'
    m=json.loads((catalog/'manifest.json').read_text(encoding='utf-8'))
    asset=next(a for a in m['assets'] if a['id']=='digit_ranked_red_9')
    source=catalog/asset['path']
    if digest(source)!=asset['sha256']:raise RuntimeError('归档9候选校验失败')
    rgb=np.array(Image.open(source).convert('RGB')).astype('float32')
    r,g,b=(rgb[:,:,i] for i in range(3))
    nine=(r>140)&(r>g*1.5)&(r>b*1.5)
    # Independently verify the saved 9 in BOTH Oct16 failure frames.
    failures=[]
    for fid in ('e9a0953937d5bf6332988733','2b3eeebbb2e4eafbc1a4271e'):
        p=ROOT/'出错任务/排位战/证据'/(fid+'.png')
        im=np.array(Image.open(p).convert('RGB'));h,w=im.shape[:2]
        region=im[int(h*.084):int(h*.145),int(w*.09):int(w*.27)].astype('float32')
        r,g,b=(region[:,:,i] for i in range(3))
        glyphs=split_glyphs((r>140)&(r>g*1.5)&(r>b*1.5))
        if len(glyphs)!=6 or not np.array_equal(glyphs[4],nine):
            raise RuntimeError('572798第5位与已标注9不一致')
        failures.append({'source':str(p.relative_to(ROOT)),'sha256':digest(p)})
    target=ROOT/'resources/local/image/ranked_power_digit9_catalog572798_4.png'
    save_new(Image.fromarray(np.where(nine,0,255).astype('uint8')),target)
    end_source=ROOT/'出错任务/排位战/证据/22e8008a8d7f470160865c92.png'
    box=[1736,912,1794,991]
    end_target=ROOT/'resources/local/image/ranked_end_label_20261015_verified.png'
    save_new(Image.open(end_source).convert('RGB').crop(box),end_target)
    result={'gameInput':False,'digit9':{'catalogSource':str(source.relative_to(ROOT)),
        'sourceSha256':digest(source),'annotatedPower':'572798','glyphIndex':4,
        'confirmedFailures':failures,'target':str(target.relative_to(ROOT)),
        'sha256':digest(target)},'endLabel':{
        'source':str(end_source.relative_to(ROOT)),'sourceSha256':digest(end_source),
        'box':box,'target':str(end_target.relative_to(ROOT)),'sha256':digest(end_target),
        'fullButtonOffset':[-68,-10,127,103],
        'note':'只取结束战斗白色文字，避开星形外侧动态战斗背景；按钮框随锚点平移。'}}
    (ROOT/'verification/ranked-oct16-template-sources.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
