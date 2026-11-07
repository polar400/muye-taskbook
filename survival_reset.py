"""Survival-only reset reading: legacy evidence plus localized 0/1 glyphs."""
from functools import lru_cache
from pathlib import Path
import re
import unicodedata

from PIL import Image

ERROR = '生存演习重置次数无法可靠识别，停止；不会按积分已满跳过'
CUTOFFS = (200, 210)


def _mask(image, cutoff):
    return (image.min(axis=2) > cutoff) & (image.max(axis=2) - image.min(axis=2) < 55)


def _normalize(mask):
    import numpy as np
    ys, xs = np.where(mask)
    if not len(xs):raise RuntimeError(ERROR + '；数字字形缺失')
    tight = mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
    return np.array(Image.fromarray(tight.astype('uint8') * 255).resize(
        (24, 40), Image.Resampling.NEAREST)) > 0


def _dilate(mask):
    import numpy as np
    padded = np.pad(mask, 1)
    return np.logical_or.reduce([padded[y:y+40, x:x+24] for y in range(3) for x in range(3)])


@lru_cache(maxsize=1)
def _references():
    import numpy as np
    folder = Path(__file__).resolve().parent / 'resources/local/survival-reset-digits'
    return {cutoff: [_normalize(_mask(np.array(Image.open(folder / f'{digit}.png').convert('RGB')), cutoff))
                     for digit in (0, 1)] for cutoff in CUTOFFS}


def _glyph(flow, anchor):
    """The numeric token is near 73% of this label, not a screen coordinate."""
    import numpy as np
    x, y, width, height = anchor['box']
    cx = x + .73 * width
    left, right = max(0, int(cx-20)), min(flow.image.shape[1], int(cx+20))
    top, bottom = max(0, y-3), min(flow.image.shape[0], y+height+3)
    crop = flow.image[top:bottom, left:right]
    observations = []
    for cutoff in CUTOFFS:
        mask = _mask(crop, cutoff)
        columns = np.flatnonzero(mask.any(axis=0))
        groups = np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1)
        possible = []
        for columns in groups:
            if not len(columns):continue
            a, b = int(columns[0]), int(columns[-1])+1
            rows = np.flatnonzero(mask[:, a:b].any(axis=1))
            t, end = int(rows[0]), int(rows[-1])+1
            if not (max(10,.3*height) <= end-t <= 1.2*height and .12 <= (b-a)/(end-t) <= .85):continue
            if abs(left+(a+b)/2-cx) > 12:continue
            glyph = _normalize(mask[t:end, a:b])
            scores = [float(((glyph & _dilate(ref)).sum()/glyph.sum()
                             + (ref & _dilate(glyph)).sum()/ref.sum())/2)
                      for ref in _references()[cutoff]]
            count = int(scores[1] > scores[0])
            if scores[count] >= .82 and scores[count]-scores[1-count] >= .12:
                possible.append({'count':count, 'scores':scores,
                                 'box':[left+a,top+t,b-a,end-t], 'cutoff':cutoff})
        if len(possible) != 1:raise RuntimeError(ERROR + '；局部数字字形未知或不唯一')
        observations.append(possible[0])
    if observations[0]['count'] != observations[1]['count']:
        raise RuntimeError(ERROR + '；两档数字字形冲突')
    return observations[0]['count'], observations


def read_survival_reset(flow):
    flow._survival_reset_evidence = None
    height, width = flow.image.shape[:2]
    anchors = flow.hits(r'重置.*余')
    values = []
    for anchor in anchors:
        # OCR often changes parentheses to 【 or ]. Ignore punctuation only;
        # missing or conflicting digits must still be proved independently.
        text = ''.join(c for c in anchor['text'] if not c.isspace()
                       and not unicodedata.category(c).startswith('P'))
        match = re.fullmatch(r'重置(?:剩)?余([01])次', text)
        x,y,w,h = anchor['box']
        if match and anchor.get('score',1) >= .8 and y > height*.8 and width*.4 < x < width*.7:
            values.append((int(match.group(1)), anchor))
    for count in (0, 1):
        matches = [m for m in flow.ocr.match(flow.image, f'survival_reset{count}', threshold=.94)
                   if m['box'][1] > height*.8 and width*.4 < m['box'][0] < width*.7]
        if len(matches) > 1:raise RuntimeError(ERROR + '；重置模板不唯一')
        if matches:values.append((count,matches[0]))
    if len(anchors) > 1 or len({count for count, _ in values}) > 1:raise RuntimeError(ERROR)
    if values:
        flow._survival_reset_evidence = {'method':'ocr_or_verified_template','count':values[0][0]}
        return values[0]
    if len(anchors) != 1:raise RuntimeError(ERROR)
    anchor = anchors[0]
    x, y, w, h = anchor['box']
    # Only a reliable, localized label can authorize a numeric glyph read.
    if not (anchor.get('score', 0) >= .8 and y > height*.8
            and width*.4 < x < width*.7 and 100 <= w <= 240 and 18 <= h <= 45):
        raise RuntimeError(ERROR)
    # A damaged surrounding word or closing bracket may itself be OCR'd as
    # a digit. Only the token between 余 and 次 is a claimed reset count.
    token = re.search(r'余(\d+)次', re.sub(r'\s+', '', anchor['text']))
    if token and token.group(1) not in ('0','1'):
        raise RuntimeError(ERROR + '；次数文案超出0或1')
    count, observations = _glyph(flow, anchor)
    if token and int(token.group(1)) != count:
        raise RuntimeError(ERROR + '；次数文案与数字字形冲突')
    flow._survival_reset_evidence = {'method':'localized_glyph', 'count':count,
                                     'anchor':anchor, 'observations':observations}
    return count, anchor
