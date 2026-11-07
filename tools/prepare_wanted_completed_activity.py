"""Preserve the user-approved missing-row state and its static visual proof."""
from pathlib import Path
from hashlib import sha256
import io
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.local_ocr import LocalOCR  # Enable bundled Pillow; no controller instance.
from PIL import Image


def keep(path,data):
    if path.exists():
        if path.read_bytes()!=data:raise RuntimeError('保留已有不同文件：'+str(path))
    else:path.write_bytes(data)


def main():
    original=Path('C:/Users/lenovo/AppData/Local/Temp/codex-clipboard-c4c65be2-72c4-4ec1-8fd9-1aba36cb0fbe.png')
    saved=ROOT/'resources/local/wanted/completed-daily-user-source.png'
    if original.exists():keep(saved,original.read_bytes())
    if not saved.exists():raise RuntimeError('缺少用户已确认的完成页面原图')
    failure=ROOT/'出错任务/通缉任务/证据/c3f691628bbbdc5d990d88a4.png'
    box=(320,335,466,473)
    crop=Image.open(failure).convert('RGB').crop(box)
    data=io.BytesIO();crop.save(data,format='PNG')
    target=ROOT/'resources/local/image/wanted_daily_completed_rows_20261018.png'
    keep(target,data.getvalue())
    manifest={'task':'wanted','userRule':'在该日常活动页面通缉条目已消失，视为通缉已完成；关闭面板后继续队列。',
              'sources':[{'path':str(saved.relative_to(ROOT)),'original':str(original),
                          'sha256':sha256(saved.read_bytes()).hexdigest(),'gameBox':[45,151,1965,1166]},
                         {'path':str(failure.relative_to(ROOT)),'sha256':sha256(failure.read_bytes()).hexdigest(),
                          'gameBox':[0,0,1920,1015]}],
              'assets':[{'path':str(target.relative_to(ROOT)),'source':str(failure.relative_to(ROOT)),
                         'sourceBox':list(box),'sha256':sha256(target.read_bytes()).hexdigest(),
                         'meaning':'通缉条目消失后，第三／四行强者降临及忍者测验的相邻静态标题；不含数字读数。'}],
              'reused':['resources/local/image/wanted_daily_selected_catalog.png','resources/local/image/close_*.png'],
              'threshold':.9}
    path=ROOT/'resources/local/wanted/completed-activity-sources.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=manifest:raise RuntimeError('保留已有不同来源记录')
    else:path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('已保存完成页面原图与来源，新增1份静态行布局模板，复用已有日常选中及关闭素材。')


if __name__=='__main__':main()
