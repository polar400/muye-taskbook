"""Verify archived pixels, references, single digits and read-only page OCR."""
from pathlib import Path
from collections import Counter
import ast
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image
import numpy as np
from tools.prepare_catalog_20261016 import CAT,DATE,SAMPLES,digest,pixel_digest,write_json
from adapters.local_ocr import LocalOCR


def check_reference(ref):
    path=CAT/ref['catalogPath'] if 'catalogPath' in ref else ROOT/ref['projectPath']
    assert path.is_file(),path
    assert digest(path)==ref['sha256'],path
    if 'manifest' in ref:
        m=json.loads((CAT/ref['manifest']).read_text(encoding='utf-8'))
        a=next(a for a in m['assets'] if a['id']==ref['assetId'])
        assert (CAT/ref['manifest']).parent/a['path']==path
    return path


def main():
    index=json.loads((CAT/'index.json').read_text(encoding='utf-8'))
    entries=[a for a in index['samples'] if a['date']==DATE]
    assert len(entries)==6
    assert len({a['id'] for a in index['samples']})==len(index['samples'])
    ocr=LocalOCR()  # ReadOnlyController: screenshot pixels only, no window IO.
    expected={
        'home':r'木叶村南|生存演习|强者降临',
        'arena':r'战令|追打状态|条件已满足',
        'timed':r'剩余奖励次数:3/3|时间:11:00-14:00',
        'ranked':r'刷新对手|调整阵容|战报',
        'daily':r'可完成任务:2/2|剩余奖励时间:1/1',
        'welfare':r'在线礼包|领取',
    }
    results=[];new_pixels={};full_source_hashes=set();total=Counter()
    for scene,(task,sid,label,_,_) in SAMPLES.items():
        folder=CAT/task/sid
        m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        source=folder/m['sourceImage'];game=folder/m['gameImage']
        assert digest(source)==m['sourceSha256']
        assert digest(source) not in full_source_hashes,'duplicate screenshot'
        full_source_hashes.add(digest(source))
        original=Image.open(source).convert('RGB');im=Image.open(game).convert('RGB')
        assert original.size==tuple(m['sourceSize']) and im.size==(1920,1015)
        assert pixel_digest(original.crop(m['gameCrop']))==pixel_digest(im)
        ids=[a['id'] for a in m['assets']+m['reusedAssets']]
        assert len(ids)==len(set(ids))
        for a in m['assets']+m['reusedAssets']:
            x,y,r,b=a['box']
            assert 0<=x<r<=1920 and 0<=y<b<=1015
            assert a['sourceBox']==[x,y+107,r,b+107]
            assert a['sourceFilename']==m['sourceFilename']
            assert a['sourceSha256']==m['sourceSha256']
            assert a['runtimeEnabled'] is False
            if a['type']=='digit':assert a['digit'] in '0123456789'
        for a in m['assets']:
            p=folder/a['path'];crop=Image.open(p).convert('RGB')
            assert list(crop.size)==a['size']
            assert digest(p)==a['sha256']
            key=pixel_digest(crop)
            assert key==a['pixelSha256']==pixel_digest(im.crop(a['box'])),p
            assert key not in new_pixels,('duplicate crop',p,new_pixels.get(key))
            new_pixels[key]=str(p)
        reasons=Counter()
        for a in m['reusedAssets']:
            p=check_reference(a['reference']);reasons[a['reuseReason']]+=1
            if a['reuseReason']=='pixel_identical':
                assert pixel_digest(Image.open(p))==pixel_digest(im.crop(a['box']))
            elif a['reuseReason']=='identical_foreground_mask':
                region=np.array(im.crop(a['box'])).astype('float32')
                r,g,b=(region[:,:,i] for i in range(3))
                mask=(r>140)&(r>g*1.5)&(r>b*1.5)
                if a['reference'].get('representation')=='existing_black_white_mask':
                    other=np.array(Image.open(p).convert('L'))<128
                else:
                    rgb=np.array(Image.open(p).convert('RGB')).astype('float32')
                    r,g,b=(rgb[:,:,i] for i in range(3))
                    other=(r>140)&(r>g*1.5)&(r>b*1.5)
                assert np.array_equal(mask,other),(scene,a['id'])
        words=ocr.read(np.array(im)[:,:,::-1].copy())
        markers=[a for a in words if a.get('score',0)>=.8 and re.search(expected[scene],a['text'])]
        assert markers,('page OCR not confirmed',scene,[a['text'] for a in words])
        if scene=='welfare':
            assert sum(a['text']=='领取' and a['score']>=.8 for a in words)==3
        if scene=='ranked':
            assert sum(a['text']=='挑战' and a['score']>=.8 for a in words)==5
        write_json(folder/'recognition-check.json',{'sampleId':sid,'gameInput':False,
            'engine':'existing LocalOCR / ReadOnlyController','words':words,
            'confirmedMarkers':markers,
            'note':'只检查画面中明确普通文字／计数字段。大号美术字未要求OCR通过，不能据此宣称新按钮／数字业务识别已验收。'})
        counts=Counter(a['type'] for a in m['assets'])
        result={'sampleId':sid,'label':label,'gameSize':list(im.size),
            'sourceHashVerified':True,'gameCropPixelEqual':True,
            'newAssets':len(m['assets']),'newDigitCrops':counts['digit'],
            'reusedAssets':len(m['reusedAssets']),'reuseReasons':dict(reasons),
            'allCropsPixelEqual':True,'allHashesAndReferencesValid':True,
            'pageOcrMarkers':[a['text'] for a in markers],
            'gameInput':False,'productionTemplatesModified':False}
        write_json(folder/'verification.json',result);results.append(result)
        total.update(newAssets=len(m['assets']),newDigitCrops=counts['digit'],reusedAssets=len(m['reusedAssets']))
    banks=json.loads((CAT/'digits/index.json').read_text(encoding='utf-8'))
    for family in banks['families']:
        keys=set(family['digits'])
        assert all(len(k)==1 and k in '0123456789' for k in keys)
        assert family['complete']==(keys==set('0123456789'))
        for ref in family['digits'].values():check_reference(ref)
    assert next(a for a in banks['families'] if a['id']=='white_serif_small')['complete']
    assert next(a for a in banks['families'] if a['id']=='ranked_red')['complete']
    baseline=json.loads((CAT/'collection-20261016-baseline.json').read_text(encoding='utf-8'))
    for p,h in baseline['files'].items():assert digest(Path(p))==h,p
    for name in ('tools/prepare_catalog_20261016.py','tools/verify_catalog_20261016.py'):
        ast.parse((ROOT/name).read_text(encoding='utf-8'),filename=name)
    report={'date':DATE,'status':'passed','samples':results,'totals':dict(total),
        'uniqueScreenshots':6,'duplicateNewPixelCrops':0,
        'preservedBaselineFiles':len(baseline['files']),
        'digitFamilies':[{'id':a['id'],'availableDigits':a['availableDigits'],
                          'missingDigits':a['missingDigits'],'complete':a['complete']} for a in banks['families']],
        'gameInput':False,'businessTestsRun':False,
        'limitations':['仅基于6张附件；没有操作游戏或补采附件外场景。',
            '页面OCR、像素与来源验证通过，不等于全部新图标已完成运行时接入。',
            '部分头像带试用／首胜原始覆盖，物品未确认名称保留外观标注。',
            '部分字形家族不满十字；不借用其他字体或合成缺字。',
            '当前全图OCR漏读多处美术字；竞技场可见剩余6个任务被读成0，福利20000／30000读作0000。仅记录，不将这些OCR值用作任务判断。']}
    write_json(CAT/'collection-20261016-verification.json',report)
    print(json.dumps({'status':'passed','totals':dict(total),
        'preservedBaselineFiles':len(baseline['files']),
        'pageMarkers':{a['sampleId']:a['pageOcrMarkers'] for a in results},
        'digitFamilies':report['digitFamilies']},ensure_ascii=False))


if __name__=='__main__':
    main()
