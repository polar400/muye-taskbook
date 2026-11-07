"""Build stable wanted-navigation crops from preserved real failure evidence."""
from pathlib import Path
from hashlib import sha256
import io
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from adapters.local_ocr import LocalOCR  # Enable bundled Pillow, without game IO.
from PIL import Image


def main():
    definitions=[
        ('resources/local/wanted/kunai-source.png',(29,15,73,49),
         'wanted_kunai_core_20261017.png','苦无金属刃和白环核心，排除发光边缘与场景背景'),
        ('出错任务/通缉任务/证据/831508e2d050f1b570feb564.png',(1185,154,1308,186),
         'wanted_detail_title_failure20261017.png','右侧活动详情的通缉任务美术字标题'),
    ]
    result={'task':'wanted','threshold':.9,'assets':[]}
    for source,box,name,label in definitions:
        path=ROOT/source
        crop=Image.open(path).convert('RGB').crop(box)
        data=io.BytesIO();crop.save(data,format='PNG')
        target=ROOT/'resources/local/image'/name
        if target.exists():
            if target.read_bytes()!=data.getvalue():raise RuntimeError('保留已有不同素材：'+name)
        else:target.write_bytes(data.getvalue())
        result['assets'].append({'path':str(target.relative_to(ROOT)),
                                'label':label,'source':source,'sourceBox':list(box),
                                'sourceSha256':sha256(path.read_bytes()).hexdigest(),
                                'sha256':sha256(target.read_bytes()).hexdigest()})
    manifest=ROOT/'resources/local/wanted/navigation-template-sources.json'
    if manifest.exists():
        if json.loads(manifest.read_text(encoding='utf-8'))!=result:raise RuntimeError('保留已有不同来源记录')
    else:manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('新增2份导航素材，保留原模板；来源与SHA256已记录。')


if __name__=='__main__':main()
