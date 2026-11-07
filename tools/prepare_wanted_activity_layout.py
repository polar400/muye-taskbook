"""Add a wanted-only completed-list variant from archived pixels, no game IO."""
from pathlib import Path
import hashlib
import io
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image


def main():
    identities=('3bbb2b405695d9d538e256a6','c16d65c386bdf5451ff4362a','d12d52e1af766a07db527f97')
    sources=[ROOT/f'出错任务/通缉任务/证据/{identity}.png' for identity in identities]
    # The 13:04 frame is the source; the two later failures are holdouts.
    box=(320,335,466,473)
    target=ROOT/'resources/local/image/wanted_daily_completed_rows_quiz_login20261019.png'
    data=io.BytesIO();Image.open(sources[0]).convert('RGB').crop(box).save(data,format='PNG')
    if target.exists() and target.read_bytes()!=data.getvalue():raise RuntimeError('拒绝覆盖不同素材')
    target.write_bytes(data.getvalue())
    manifest={'task':'wanted','threshold':.9,'roi':[.14,.3,.3,.49],
              'meaning':'日常已完成条目移除强者降临后，第三行忍者测验＋第四行登录；保留所有原终态检查。',
              'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                          'role':'template source' if i==0 else 'holdout'} for i,p in enumerate(sources)],
              'asset':{'path':target.relative_to(ROOT).as_posix(),'source':sources[0].relative_to(ROOT).as_posix(),
                       'sourceBox':list(box),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},
              'loader':'LocalOCR.match loads wanted_daily_completed_rows_*.png without shared-code changes'}
    path=ROOT/'resources/local/wanted/completed-activity-layout-20261019.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=manifest:raise RuntimeError('拒绝覆盖不同来源')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(target)


if __name__=='__main__':main()
