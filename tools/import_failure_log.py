"""Import an explicitly selected historical log without modifying the log."""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT)]
from failure_archive import import_log,FailureArchive

parser=argparse.ArgumentParser()
parser.add_argument('log',type=Path)
args=parser.parse_args()
count=import_log(ROOT,args.log)
archive=FailureArchive(ROOT);archive.refresh()
summary=json.loads((archive.folder/'统计.json').read_text(encoding='utf-8'))
print(json.dumps({'imported':count,'errors':summary['errorCount'],'interruptions':summary['interruptionCount'],'tasks':summary['tasks']},ensure_ascii=False,indent=2))
