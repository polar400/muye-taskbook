"""Offline replay of the single lower acceptance trial; no desktop APIs."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'vendor'))
import numpy as np
from PIL import Image
from adapters.local_ocr import LocalOCR
from arena_daily import DailyVision,board_key


def main():
    source='verification/arena-lower-virtual-20261020-011916-475721'
    folder=ROOT/source;live=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    ocr=LocalOCR();vision=DailyVision(ocr);rows=[]
    for name in ('00-before.png','01-before.png','02-open-lower.png','03-open-lower.png'):
        image=np.array(Image.open(folder/name).convert('RGB'))[:,:,::-1].copy()
        start=time.perf_counter();ocr.read(image);full=time.perf_counter()-start
        start=time.perf_counter();board=vision.read(image[350:790,90:342].copy(),(90,350));local=time.perf_counter()-start
        rows.append(dict(file=name,fullOcrSeconds=round(full,4),boardSeconds=round(local,4),
                         hovered=[c['hovered'] for c in board['cards']] if board else None,
                         sameTaskKey=bool(board and board_key(board)==board_key(live['boardBefore'])),board=board))
    report=dict(scope='仅保存实图离线重读，不调用窗口或进程API',source=source,gameInputs=0,
        liveResult=live['result'],error=live['error'],inputAttempts=live['inputAttempts'],
        restored=all(p['restored'] for p in live['phases']),cursorUnchanged=live['cursorUnchanged'],
        foregroundUnchanged=live['foregroundUnchanged'],rows=rows,
        limitations=['离线耗时不含实际截图、PNG保存及进程入口准备，不能重建真实逐步时序',
                     '本次两帧仍未满足，没有复现前次悬停成功；不能归因仅为OCR或时间预算'])
    out=ROOT/'verification/arena-lower-virtual-offline-20261020.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(result=live['result'],inputAttempts=live['inputAttempts'],restored=report['restored'],
        rows=[{k:r[k] for k in ('file','fullOcrSeconds','boardSeconds','hovered','sameTaskKey')} for r in rows]),ensure_ascii=True))


if __name__=='__main__':main()
