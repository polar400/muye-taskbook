"""Archive supplied wanted-task images and promote only new runtime assets."""
from pathlib import Path
from hashlib import sha256
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.local_ocr import LocalOCR  # Set up bundled Pillow dependency path.
from PIL import Image

SOURCES={
 'kunai':'91fa01c3-f2d4-491d-a632-4d68a085926b',
 'daily':'f3e82937-7238-42e7-ad46-b53bebb9ce4d',
 'row':'2163fe81-8bfd-421c-9ce1-daaebcbe25d2',
 'participate':'7001344c-27b7-4f42-9030-fc62af7773e7',
 'panel':'43124e5d-883a-4892-b019-001aa0ccf024',
}

def write_new(path,data):
    if path.exists():
        if path.suffix=='.json' and json.loads(path.read_text(encoding='utf-8'))==json.loads(data):return
        if path.read_bytes()!=data:raise RuntimeError('保留已有文件，内容不同：'+str(path))
    else:path.write_bytes(data)

def main():
    folder=ROOT/'resources/local/wanted';folder.mkdir(exist_ok=True)
    runtime=ROOT/'resources/local/image'
    manifest={'task':'wanted','sources':{},'assets':[],
              'gameCrop':[0,107,1920,1122],
              'userRules':'自动完成免费；点击自动完成后确认是一次，游戏自动接取并完成全部；最终今日余下次数0。'}
    for key,uid in SOURCES.items():
        name='codex-clipboard-'+uid+'.png'
        original=Path('C:/Users/lenovo/AppData/Local/Temp')/name
        target=folder/(key+'-source.png')
        if not target.exists():write_new(target,original.read_bytes())
        manifest['sources'][key]={'originalFilename':name,'path':str(target.relative_to(ROOT)),
                                  'sha256':sha256(target.read_bytes()).hexdigest(),
                                  'size':list(Image.open(target).size)}
    def crop(key,box,name):
        picture=Image.open(folder/(key+'-source.png')).convert('RGB').crop(box)
        path=runtime/(name+'_user.png')
        import io
        buffer=io.BytesIO();picture.save(buffer,format='PNG');write_new(path,buffer.getvalue())
        manifest['assets'].append({'path':str(path.relative_to(ROOT)),'source':key,'sourceBox':list(box),
                                   'sha256':sha256(path.read_bytes()).hexdigest()})
    crop('kunai',(23,0,80,59),'wanted_kunai')
    crop('daily',(0,0,210,72),'wanted_daily')
    crop('row',(45,20,195,75),'wanted_row')
    crop('participate',(58,4,226,58),'wanted_participate')
    crop('panel',(812,218,1155,291),'wanted_title')
    crop('panel',(1230,355,1405,410),'wanted_auto')
    crop('panel',(1530,274,1583,326),'wanted_close')
    crop('panel',(821,362,1059,400),'wanted_counter')
    daily=ROOT/'resources/local/catalog/activities/20261016-973-daily'
    for old,name in [('tab_daily.png','wanted_daily_selected_catalog.png'),
                     ('event_label_3.png','wanted_row_catalog.png'),
                     ('participate.png','wanted_participate_catalog.png')]:
        source=daily/old;path=runtime/name;write_new(path,source.read_bytes())
        manifest['assets'].append({'path':str(path.relative_to(ROOT)),
                                   'reusedFrom':str(source.relative_to(ROOT)),
                                   'manifest':str((daily/'manifest.json').relative_to(ROOT)),
                                   'sha256':sha256(path.read_bytes()).hexdigest()})
    picture=Image.open(folder/'panel-source.png').crop((0,107,1920,1122))
    import io
    buffer=io.BytesIO();picture.save(buffer,format='PNG');write_new(folder/'panel-game.png',buffer.getvalue())
    text=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    write_new(folder/'manifest.json',text.encode('utf-8'))
    print('5份原始附件已保留，11份运行素材已建立来源记录。')

if __name__=='__main__':main()
