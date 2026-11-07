"""Preserve supplied auto-path evidence and reuse its small original as template."""
from pathlib import Path
from hashlib import sha256
import io
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)];sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image


def keep(path,data):
    if path.exists():
        if path.read_bytes()!=data:raise RuntimeError('保留已有不同文件：'+str(path))
    else:path.write_bytes(data)


def main():
    inputs=[
      ('codex-clipboard-abcfd631-3355-45c1-8af0-6b09b8eef45d.png','resources/local/wanted/autopath-home-user-source.png'),
      ('codex-clipboard-fab8420b-a603-459f-99bc-41ffdffecbf0.png','resources/local/wanted/autopath-label-user-source.png'),
      ('codex-clipboard-604d768c-f61c-45e4-8ec7-3a63805938c5.png','resources/local/image/wanted_autopath_label_user20261019.png')]
    sources=[]
    for original,target in inputs:
        src=Path('C:/Users/lenovo/AppData/Local/Temp')/original;dst=ROOT/target
        if src.exists():keep(dst,src.read_bytes())
        if not dst.exists():raise RuntimeError('缺少用户素材：'+original)
        with Image.open(dst) as im:size=list(im.size)
        sources.append({'originalFilename':original,'path':target,'sha256':sha256(dst.read_bytes()).hexdigest(),'size':size})
    box=[45,151,1965,1166]
    with Image.open(ROOT/inputs[0][1]) as im:game=im.convert('RGB').crop(box)
    data=io.BytesIO();game.save(data,format='PNG')
    target='resources/local/wanted/autopath-home-game.png';keep(ROOT/target,data.getvalue())
    manifest={'task':'wanted','gameInput':False,'sources':sources,
              'gameImage':target,'gameCrop':box,'gameSha256':sha256((ROOT/target).read_bytes()).hexdigest(),
              'assets':[{'path':inputs[2][1],'source':inputs[2][1],'sourceBox':[0,0,249,49],
                         'meaning':'用户提供的自动寻路中文字原片，原字节直接作为运行模板，不重复裁剪。'}],
              'runtimeTemplatesAdded':1,'threshold':.9,'roi':[.36,.08,.6,.2]}
    path=ROOT/'resources/local/wanted/autopath-sources.json'
    keep(path,(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'manifest':str(path),'runtimeTemplatesAdded':1},ensure_ascii=False))


if __name__=='__main__':main()
