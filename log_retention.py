"""Keep runtime logs and incident backups for 15 Beijing calendar days."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re

BEIJING=timezone(timedelta(hours=8))
def local_day():
    return datetime.now(BEIJING).date()

def maintain_logs(root,today=None):
    from failure_archive import FailureArchive, LABELS
    root=Path(root).resolve();today=today or local_day()
    cutoff=today-timedelta(days=14)
    deleted=[]
    folder=root/'logs'
    if folder.exists():
        dated=[]
        for p in folder.iterdir():
            if not p.is_file() or p.is_symlink():continue
            match=re.match(r'^(\d{4}-\d{2}-\d{2})(?:\D|$)',p.name)
            try:day=datetime.strptime(match[1],'%Y-%m-%d').date() if match else datetime.fromtimestamp(p.stat().st_mtime,BEIJING).date()
            except ValueError:continue
            if day<cutoff:dated.append((day,p))
        for _,p in sorted(dated):
            p.unlink();deleted.append(str(p.relative_to(root)))
    if not (root/'出错任务').exists():return deleted
    archive=FailureArchive(root)
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        keep=[];expired=[]
        for row in db.execute('SELECT payload FROM incidents ORDER BY rowid'):
            item=json.loads(row[0])
            try:
                moment=datetime.fromisoformat(item['occurredAt'])
                day=(moment.replace(tzinfo=BEIJING) if moment.tzinfo is None else moment.astimezone(BEIJING)).date()
            except (ValueError,KeyError):
                keep.append(item);continue
            (expired if day<cutoff else keep).append(item)
        for item in sorted(expired,key=lambda r:r['occurredAt']):
            ident=item['id'];label=LABELS.get(item['taskId'])
            if label and re.fullmatch(r'[\w-]+',ident):
                base=archive.folder/label
                files=[base/'记录'/(ident+suffix) for suffix in ('.json','.md')]
                files.extend((base/'证据').glob(ident+'.*'))
                for p in files:
                    if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(archive.folder):
                        p.unlink();deleted.append(str(p.relative_to(root)))
            db.execute('DELETE FROM incidents WHERE id=?',(ident,))
        if expired:
            ids={r['id'] for r in keep}
            for item in keep:
                item['similarIds']=[i for i in item.get('similarIds',[]) if i in ids]
                item['similarCount']=len(item['similarIds'])
                db.execute('UPDATE incidents SET payload=? WHERE id=?',(json.dumps(item,ensure_ascii=False),item['id']))
            for label in LABELS.values():
                if not any(r['taskName']==label for r in keep):
                    (archive.folder/label/'任务统计.md').unlink(missing_ok=True)
            archive.export(keep)
    return deleted
