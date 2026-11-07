"""Extract the manually verified 8 from the 2026-10-13 afternoon failure.

572882 is a source annotation, never a runtime power setting. The two 8 masks
must agree; the archived screenshot and all existing templates are preserved.
This tool reads files only and has no game controller.
"""
from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ranked_vision import split_glyphs
from PIL import Image
import numpy as np


def main():
    source=ROOT/'出错任务/排位战/证据/1d6c05e9d6c508ef8460ef10.png'
    image=np.array(Image.open(source).convert('RGB'))
    if image.shape[:2]!=(1015,1920):
        raise RuntimeError('排位战失败原图必须为1920×1015')
    height,width=image.shape[:2]
    region=image[int(height*.084):int(height*.145),int(width*.09):int(width*.27)].astype('float32')
    r,g,b=(region[:,:,i] for i in range(3))
    glyphs=split_glyphs((r>140)&(r>g*1.5)&(r>b*1.5))
    if len(glyphs)!=6 or not np.array_equal(glyphs[3],glyphs[4]):
        raise RuntimeError('已核对的572882字形数量或两个8的像素不一致')
    pixels=np.where(glyphs[3],0,255).astype('uint8')
    target=ROOT/'resources/local/image/ranked_power_digit8_failure572882_3.png'
    if target.exists():
        if not np.array_equal(np.array(Image.open(target).convert('L')),pixels):
            raise RuntimeError('已有8模板与失败原图不一致，保留原文件')
    else:
        Image.fromarray(pixels).save(target)
    print(json.dumps({'source':str(source.relative_to(ROOT)),
                      'source_sha256':sha256(source.read_bytes()).hexdigest(),
                      'annotation':'572882','glyph_indices':[3,4],
                      'glyph_shape':list(pixels.shape),
                      'template':str(target.relative_to(ROOT)),
                      'template_sha256':sha256(target.read_bytes()).hexdigest()},ensure_ascii=False))


if __name__=='__main__':
    main()
