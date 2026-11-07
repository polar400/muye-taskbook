"""Archive six user attachments and exact icon/digit crops; never opens a game.

Source coordinates are annotations for reconstruction, not click targets.
Existing semantic assets and pixel-identical glyphs are referenced, not copied.
"""
from pathlib import Path
from hashlib import sha256
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
sys.path.insert(0,str(ROOT))
from PIL import Image, ImageDraw, ImageFont
import numpy as np

CAT=ROOT/'resources/local/catalog'
DATE='2026-10-16'
SAMPLES={
 'home':('home','20261016-973-village','主界面','木叶村南，菜单展开','379f1978-262d-4dac-9d9e-c58e97c0b36e'),
 'arena':('arena','20261016-973-team-ready','竞技场','我的忍者／阵容与任务','d15ef6f2-826e-452d-a61d-e5a4980786bf'),
 'timed':('activities','20261016-973-timed','限时活动','限时活动选中，参与灰色','0077cc10-013d-4f12-a497-18e394c3c0a9'),
 'ranked':('ranked','20261016-973-cross-ready','排位战','联服，剩余5次，刷新可用','77e57b41-2e02-420f-bdbd-8038c2e469e5'),
 'daily':('activities','20261016-973-daily','日常活动','日常活动选中，参与可用','1fe45c5c-9b9a-46b5-b944-7188d6080bb0'),
 'welfare':('welfare','20261016-973-online-gift','福利大厅','在线礼包，三个领取按钮可见','3163deb0-8d89-482e-bcd0-bfd42aaf58aa'),
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def pixel_digest(im):
    im=im.convert('RGB')
    return sha256(str(im.size).encode()+im.tobytes()).hexdigest()


def save_image(im,path,revise=False):
    if path.exists():
        if pixel_digest(Image.open(path))!=pixel_digest(im):
            # Only this batch's annotated candidate crops may be corrected.
            # Source screenshots, game crops and all older assets stay immutable.
            assert revise and path.parent.name in {s[1] for s in SAMPLES.values()}
            im.save(path)
    else:
        im.save(path)


def write_json(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)


class Collection:
    def __init__(self):
        self.samples={}
        self.known={}
        self.pixels={}
        self.digits={}
        self.prior_hashes={}
        index=json.loads((CAT/'index.json').read_text(encoding='utf-8'))
        for entry in index['samples']:
            if entry['date']==DATE:
                continue  # Rebuild today's metadata reproducibly, preserving files.
            path=CAT/entry['manifest']
            data=json.loads(path.read_text(encoding='utf-8'))
            for p in (path,path.parent/data['gameImage']):
                self.prior_hashes[str(p)]=digest(p)
            for asset in data['assets']:
                p=path.parent/asset['path']
                ref={'catalogPath':p.relative_to(CAT).as_posix(),
                     'manifest':entry['manifest'],'assetId':asset['id'],
                     'sha256':digest(p)}
                self.prior_hashes[str(p)]=digest(p)
                self.known[(data['task'],asset['id'])]=ref
                self.pixels.setdefault(pixel_digest(Image.open(p)),ref)
        # Existing ranked digit masks are already verified; reference their files.
        for p in sorted((ROOT/'resources/local/image').glob('ranked_power_digit*_*.png')):
            digit=p.name.split('digit')[1][0]
            im=Image.open(p).convert('L')
            mask=np.array(im)<128
            key=(mask.shape,mask.tobytes())
            ref={'projectPath':p.relative_to(ROOT).as_posix(),'sha256':digest(p),
                 'sourceDocumentation':'resources/local/来源说明.md',
                 'representation':'existing_black_white_mask'}
            self.digits.setdefault(key,ref)
            self.known.setdefault(('digits','ranked_red_'+digit),ref)
            self.prior_hashes[str(p)]=digest(p)
        for name in ('config.json','run.json','app.py','native_worker.py',
                     'local_flows.py','ranked_vision.py','ranked_pipeline.py'):
            p=ROOT/name
            self.prior_hashes[str(p)]=digest(p)
        for key,(task,sid,label,state,stem) in SAMPLES.items():
            source=Path('C:/Users/lenovo/AppData/Local/Temp')/('codex-clipboard-'+stem+'.png')
            folder=CAT/task/sid
            folder.mkdir(parents=True,exist_ok=True)
            original=Image.open(source).convert('RGB')
            assert original.size==(1965,1167),(source,original.size)
            source_copy=folder/'source.png'
            if source_copy.exists():
                assert digest(source_copy)==digest(source)
            else:
                source_copy.write_bytes(source.read_bytes())
            game=original.crop((0,107,1920,1122))
            save_image(game,folder/'game.png')
            self.samples[key]={'folder':folder,'image':game,'manifest':{
                'id':sid,'task':task,'label':label,'date':DATE,'accountServer':'973',
                'scope':label,'state':state,'sourceFilename':source.name,
                'sourceSha256':digest(source),'sourceSize':list(original.size),
                'sourceImage':'source.png','gameCrop':[0,107,1920,1122],
                'gameImage':'game.png','gameSize':[1920,1015],
                'assets':[],'reusedAssets':[],'gameInput':False,
                'notes':['只从用户附件离线提取，未操作游戏；裁切坐标不是点击目标。',
                         '已有同功能同状态图标复用引用；语义复用不声称当前画面像素相同。',
                         '数字逐字保存并标注字体样式；不固定业务读数。',
                         '素材候选未自动接入resources/local/image，未改变任务执行。',
                         '日期为接收／整理日期，不推定附件拍摄时间。']}}

    def add(self,scene,aid,label,box,kind='icon',state='正常',reuse=None,**extra):
        sample=self.samples[scene];m=sample['manifest']
        assert not any(a['id']==aid for a in m['assets']+m['reusedAssets']),aid
        x,y,r,b=box
        assert 0<=x<r<=1920 and 0<=y<b<=1015,(scene,aid,box)
        crop=sample['image'].crop(box)
        asset={'id':aid,'label':label,'state':state,'type':kind,'box':list(box),
               'sourceFilename':m['sourceFilename'],'sourceSha256':m['sourceSha256'],
               'sourceBox':[x,y+107,r,b+107],'runtimeEnabled':False,**extra}
        ref=self.known.get(reuse) if reuse else None
        reason='existing_semantic_same_state' if ref else None
        if not ref:
            ref=self.pixels.get(pixel_digest(crop))
            if ref:reason='pixel_identical'
        if ref:
            asset.update(reference=ref,reuseReason=reason)
            m['reusedAssets'].append(asset)
            return ref
        path=sample['folder']/(aid+'.png')
        save_image(crop,path,revise=True)
        asset.update(path=path.name,size=list(crop.size),sha256=digest(path),
                     pixelSha256=pixel_digest(crop))
        m['assets'].append(asset)
        ref={'catalogPath':path.relative_to(CAT).as_posix(),
             'manifest':(sample['folder']/'manifest.json').relative_to(CAT).as_posix(),
             'assetId':aid,'sha256':digest(path)}
        self.known[(m['task'],aid)]=ref
        self.pixels[pixel_digest(crop)]=ref
        return ref

    def reuse_old(self,scene,task,skip=()):
        path=CAT/('home/20261013-974-village/manifest.json' if task=='home' else 'ranked/20261013-974-cross-ready/manifest.json')
        data=json.loads(path.read_text(encoding='utf-8'))
        for a in data['assets']:
            if a['type']=='dynamic_region' or a['id'] in skip:continue
            box=list(a['box'])
            # Home row 3 currently has three icons at the right, not four.
            if scene=='home' and a['id'] in ('treasure','privilege_events','benefits'):
                box={'treasure':[1288,204,1380,312],
                     'privilege_events':[1380,204,1468,312],
                     'benefits':[1468,204,1559,312]}[a['id']]
            self.add(scene,a['id'],a['label'],box,a['type'],a['state'],reuse=(task,a['id']))

    def digit(self,scene,family,char,box,mask=None,occurrence=None):
        assert char in '0123456789'
        sample=self.samples[scene];m=sample['manifest']
        aid=f'digit_{family}_{char}'
        suffix=sum(a['id'].startswith(aid) for a in m['assets']+m['reusedAssets'])
        if suffix:aid+=f'_{suffix}'
        ref=self.digits.get((mask.shape,mask.tobytes())) if mask is not None else None
        if ref:
            x,y,r,b=box
            m['reusedAssets'].append({'id':aid,'label':f'{family} 单字 {char}',
              'state':'已有同像素红色字形掩码','type':'digit','digit':char,'family':family,
              'box':list(box),'sourceBox':[x,y+107,r,b+107],
              'sourceFilename':m['sourceFilename'],'sourceSha256':m['sourceSha256'],
              'runtimeEnabled':False,'reference':ref,'reuseReason':'identical_foreground_mask',
              'occurrence':occurrence})
            return
        ref=self.add(scene,aid,f'{family} 单字 {char}',box,'digit','来源实像素',
                     reuse=('digits',family+'_'+char),digit=char,family=family,
                     occurrence=occurrence)
        self.known[('digits',family+'_'+char)]=ref
        if mask is not None and any(a['id']==aid for a in m['assets']):
            self.digits[(mask.shape,mask.tobytes())]=ref

    def red_digits(self,scene,box,text,family):
        a=np.array(self.samples[scene]['image'].crop(box)).astype('float32')
        r,g,b=(a[:,:,i] for i in range(3))
        mask=(r>140)&(r>g*1.5)&(r>b*1.5)
        spans=[];start=None
        for x,hit in enumerate([*np.any(mask,axis=0),False]):
            if hit and start is None:start=x
            if not hit and start is not None:
                ys,_=np.where(mask[:,start:x]);spans.append((start,int(ys.min()),x,int(ys.max()+1)));start=None
        assert len(spans)==len(text),(scene,text,spans)
        for i,(char,(x,y,r,b)) in enumerate(zip(text,spans)):
            self.digit(scene,family,char,(box[0]+x,box[1]+y,box[0]+r,box[1]+b),
                       mask[y:b,x:r],{'text':text,'index':i,'method':'red_mask_projection'})

    def finish(self):
        entries=[]
        families={}
        for key,sample in self.samples.items():
            m=sample['manifest'];folder=sample['folder']
            write_json(folder/'manifest.json',m)
            assets=m['assets']
            for a in assets+m['reusedAssets']:
                if a['type']!='digit':continue
                if a in assets:
                    ref={'catalogPath':(folder/a['path']).relative_to(CAT).as_posix(),
                         'manifest':(folder/'manifest.json').relative_to(CAT).as_posix(),
                         'assetId':a['id'],'sha256':a['sha256'],
                         'representation':'source_rgb_crop'}
                else:
                    ref=a['reference']
                families.setdefault(a['family'],{}).setdefault(a['digit'],ref)
            cols=5;cellw=330;cellh=165
            sheet=Image.new('RGB',(cols*cellw,max(1,(len(assets)+cols-1)//cols)*cellh),'#e7e9ee')
            draw=ImageDraw.Draw(sheet)
            for i,a in enumerate(assets):
                x=(i%cols)*cellw;y=(i//cols)*cellh
                im=Image.open(folder/a['path']).convert('RGB')
                im.thumbnail((310,115))
                if a['type']=='digit':
                    im=Image.open(folder/a['path']).convert('RGB')
                    factor=min(4,100/max(im.size))
                    im=im.resize((round(im.width*factor),round(im.height*factor)),Image.Resampling.NEAREST)
                sheet.paste(im,(x+10,y+8))
                draw.text((x+8,y+122),a['id'][:46],font=font(11),fill='black')
                draw.text((x+8,y+140),a['label'][:27],font=font(13),fill='black')
            sheet.save(folder/'contact-sheet.png')
            entries.append({'id':m['id'],'task':m['task'],'scope':m['scope'],
                'state':m['state'],'manifest':(folder/'manifest.json').relative_to(CAT).as_posix(),
                'image':(folder/'game.png').relative_to(CAT).as_posix(),'date':DATE})
        index=json.loads((CAT/'index.json').read_text(encoding='utf-8'))
        ids={a['id'] for a in entries}
        index['samples']=[a for a in index['samples'] if a['id'] not in ids]+entries
        write_json(CAT/'index.json',index)
        for p,h in self.prior_hashes.items():assert digest(Path(p))==h,p
        # Complete the ranked-red lookup by referencing already verified masks.
        # Keep their representation explicit: RGB crops and binary masks differ.
        for digit in '012345678':
            if digit in families['ranked_red']:continue
            p=next(iter(sorted((ROOT/'resources/local/image').glob(f'ranked_power_digit{digit}_*.png'))))
            families['ranked_red'][digit]={'projectPath':p.relative_to(ROOT).as_posix(),
                'sha256':digest(p),'sourceDocumentation':'resources/local/来源说明.md',
                'representation':'existing_black_white_mask'}
        folder=CAT/'digits';folder.mkdir(exist_ok=True)
        write_json(folder/'index.json',{'version':1,'date':DATE,'order':'1234567890',
            'gameInput':False,'runtimeEnabled':False,
            'notes':['只保存或引用真实可见的逐字字形；缺字不合成、不跨字体补齐。',
                     'white_serif_small全套来自当前排位榜；ranked_red为既有掩码和新原色字形引用。',
                     '同数字的不同字体／尺寸分家族，使用时须匹配family和representation。'],
            'families':[{'id':key,'availableDigits':''.join(d for d in '1234567890' if d in refs),
                         'missingDigits':''.join(d for d in '1234567890' if d not in refs),
                         'complete':set(refs)==set('0123456789'),
                         'digits':{d:refs[d] for d in '1234567890' if d in refs}}
                        for key,refs in sorted(families.items())]})
        write_json(CAT/'collection-20261016-baseline.json',{
            'date':DATE,'files':self.prior_hashes,
            'purpose':'生成前基线：旧catalog原图／manifest／裁切、运行字形、配置与相关执行代码；生成后及验证时检查未变'})
        print(json.dumps({k:{'new':len(v['manifest']['assets']),
                              'reused':len(v['manifest']['reusedAssets'])}
                          for k,v in self.samples.items()},ensure_ascii=False))


def main():
    c=Collection()
    c.reuse_old('home','home',skip=('first_recharge','world_menu'))
    c.reuse_old('ranked','ranked')
    for aid,label,box in [
      ('profile_avatar','角色头像',[0,0,130,161]),
      ('coin','铜币图标',[124,127,168,171]),('coupon','点券图标',[275,123,327,171]),
      ('ingot','元宝图标',[410,125,450,169]),
      ('sun_mark','日之印标识',[460,8,495,49]),('moon_mark','月之印标识',[506,7,541,49]),
      ('toolbar_expand','工具栏展开柄',[1559,8,1593,84]),
      ('toolbar_friends','社交工具图标',[1594,9,1635,62]),
      ('toolbar_handshake','握手工具图标',[1634,9,1675,62]),
      ('toolbar_mail','邮件图标',[1676,10,1717,62]),
      ('toolbar_briefcase','公文包工具图标',[1717,10,1756,62]),
      ('toolbar_help','帮助图标',[1757,9,1797,62]),
      ('toolbar_link','链环工具图标',[1797,9,1837,62]),
      ('toolbar_headset','耳机工具图标',[1837,9,1878,62]),
      ('toolbar_swirl','旋涡工具图标',[1878,9,1919,62]),
      ('chat_ninja','聊天忍者图标',[525,939,576,989]),
      ('chat_bubbles','聊天气泡图标',[575,939,624,989]),
      ('chat_expand','聊天栏展开箭头',[220,872,285,902]),
      ('quest_auto','任务自动标记',[1811,528,1858,552]),
    ]:c.add('home',aid,label,box)

    # Ranked portraits and rank insignia were not individually archived before.
    for i,x in enumerate((135,196,257,318)):
        for row,y in enumerate((245,327,411)):
            c.add('ranked',f'team_portrait_{row+1}_{i+1}',f'排位阵容第{row+1}行第{i+1}头像',
                  [x,y,x+59,y+59],'portrait')
    for i,box in enumerate(([717,150,784,243],[717,250,784,342],[717,350,784,442])):
        c.add('ranked',f'rank_emblem_{i+1}',f'排行榜第{i+1}名美术字',box,'digit',digit=str(i+1),family='rank_emblem')
    c.add('ranked','leader_portrait','排行榜头像（前两名同外观复用）',[784,150,874,243],'portrait')
    c.add('ranked','leader_portrait_third','排行榜第三名头像',[784,350,874,442],'portrait')
    for i,box in enumerate(([64,258,109,298],[64,340,109,380],[64,422,109,462])):
        c.add('ranked',f'team_lane_{i}',('阵容上路','阵容中路','阵容下路')[i],box,'page_marker')

    arena=[
      ('rank_medal','竞技场段位徽章',[74,86,357,278],'page_marker'),
      ('my_ninjas_title','我的忍者标题',[1084,128,1319,181],'page_marker'),
      ('reward','段位奖励按钮',[278,273,340,311],'button'),
      ('tab_arena','竞技场页签',[1383,0,1528,94],'button'),
      ('tab_finals','巅峰赛页签（灰色）',[1528,0,1665,94],'button'),
      ('tab_training','主角训练页签',[1665,0,1795,94],'button'),
      ('help_book','玩法说明书',[1796,27,1854,85],'button'),
      ('filter_stars','星级筛选',[1080,186,1168,229],'button'),
      ('filter_dropdown_arrow','筛选下拉箭头',[1133,193,1164,226],'icon'),
      ('filter_element','属性筛选',[1170,186,1307,229],'button'),
      ('filter_chase','追打状态筛选',[1309,186,1452,229],'button'),
      ('filter_cause','造成状态筛选',[1454,186,1595,229],'button'),
      ('filter_chakra','查克拉筛选',[1597,186,1709,229],'button'),
      ('search','输入忍者名字',[1711,186,1870,229],'button'),
      ('scroll_up','忍者列表向上',[1835,244,1884,291],'button'),
      ('scroll_down','忍者列表向下',[1834,906,1884,955],'button'),
      ('scroll_thumb','忍者列表滚动滑块',[1845,291,1876,369],'control'),
      ('condition_met','条件已满足标记',[222,491,322,521],'page_marker'),
      ('task_reward','竞技场任务奖励图标（含数量角标）',[128,479,214,563],'reward_icon'),
      ('main_talent','主角天赋',[392,670,502,709],'button'),
      ('treasure_tab','宝具页签',[511,670,620,709],'button'),
      ('ranking_button','排行榜按钮',[901,670,1013,709],'button'),
      ('trial_record','试玩阵容独立记录标记',[684,668,880,710],'page_marker'),
      ('ranked_battle','段位战斗按钮',[415,872,680,971],'button'),
      ('casual_battle','休闲战斗按钮',[715,872,970,971],'button'),
      ('first_win','首胜角标',[1097,367,1156,420],'page_marker'),
      ('star','忍者星级单颗星',[1237,260,1267,294],'icon'),
      ('element_wind','风属性图标',[1299,289,1337,326],'icon'),
      ('element_earth','土属性图标',[1541,289,1581,326],'icon'),
      ('element_fire','火属性图标',[1299,408,1337,445],'icon'),
      ('element_water','水属性图标',[1299,525,1337,562],'icon'),
      ('element_lightning','雷属性图标',[1793,758,1832,795],'icon'),
    ]
    for aid,label,box,kind in arena:c.add('arena',aid,label,box,kind)
    c.add('arena','close_panel','关闭面板',[1854,27,1911,84],'button',reuse=('ranked','close_panel'))
    c.add('arena','shop','杂货屋',[112,787,326,872],'button',reuse=('ranked','shop'))
    names=['手鞠[泳装]','井野[泳装]','角都[地怨虞]','伊鲁卡','大蛇丸[木叶的叛忍]',
           '大蛇丸[三忍大战]','羽高[秽土转生]','羽高[六尾人柱力]',
           '鬼灯幻月[二代水影·秽土转生]','宇智波止水[须佐能乎]',
           '由木人[二尾人柱力]','矢仓[秽土转生]','野原琳','井野[夏装]',
           '凯[惊门]','红豆[新春]','佩恩·修罗道','团藏[代理火影]']
    for i,name in enumerate(names):
        col=i%3;row=i//3;x=1100+col*248;y=250+row*117
        c.add('arena',f'ninja_portrait_{i+1:02d}',name,[x,y,x+97,y+87],
              'portrait','试用或首胜角标按原图保留，非纯净头像')
    for i,(x,w) in enumerate(((393,71),(464,77),(550,71),(621,77),(708,70),(778,77),(861,72),(933,79))):
        c.add('arena',f'skill_slot_{i+1}',f'阵容技能栏第{i+1}图标',[x+3,724,x+w-3,778],'skill_icon')

    for scene in ('timed','daily'):
        for aid,label,box,kind in [
          ('calendar','活动周历',[1415,80,1553,128],'button'),
          ('scroll_up','活动列表向上',[1121,155,1151,192],'button'),
          ('scroll_down','活动列表向下',[1121,711,1151,750],'button'),
          ('frog_available','绿色活跃奖励蛙',[466,759,570,842],'reward_state'),
          ('frog_locked','灰色活跃奖励蛙',[1222,759,1325,842],'reward_state'),
          ('sun_currency','日之印图标',[293,907,379,994],'currency_icon'),
          ('moon_currency','月之印图标',[735,907,823,994],'currency_icon'),
          ('shop_activity','活动杂货屋入口',[1433,909,1577,1002],'button'),
        ]:c.add(scene,aid,label,box,kind,reuse=('activities',aid))
        c.add(scene,'close_panel','活动面板关闭',[1617,15,1674,74],'button',reuse=('ranked','close_panel'))
        c.add(scene,'tab_daily','日常活动',[297,55,502,133],'button',
              '选中' if scene=='daily' else '未选中')
        c.add(scene,'tab_timed','限时活动',[503,55,707,133],'button',
              '选中' if scene=='timed' else '未选中')
        c.add(scene,'tab_recommended','今日推荐',[708,55,914,133],'button',
              '未选中',reuse=('activities','tab_recommended'))
        c.add(scene,'participate','参与按钮',[1267,689,1440,741],'button',
              '灰色' if scene=='timed' else '可用')
    timed_names=['羁绊对决','神秘劫镖','拯救人柱力','喵问答','组队副本','试炼之地']
    for i,label in enumerate(timed_names):
        y=198+i*86
        c.add('timed',f'event_icon_{i+1}',label+'图标',[1020,y,1108,y+81])
        c.add('timed',f'event_label_{i+1}',label+'文字入口',[304,y+12,477,y+66],'text_button')
    for aid,label,box in [
      ('event_large','羁绊对决大图标',[1251,175,1473,375]),
      ('reward_silver_many','大量月之印奖励',[1234,607,1307,677]),
      ('reward_special_gold','特殊金色随机奖励',[1312,607,1385,677]),
      ('reward_special_red','特殊红色随机奖励',[1390,607,1464,677]),
    ]:c.add('timed',aid,label,box,'reward_icon')
    daily_names=['竞技场','泡温泉','通缉任务','忍者测验','登录','忍者考试','丰饶之间']
    for i,label in enumerate(daily_names):
        y=153+i*86
        c.add('daily',f'event_icon_{i+1}',label+'图标',[1020,y,1108,y+81],
              'icon','已完成角标' if i>=4 else '正常')
        c.add('daily',f'event_label_{i+1}',label+'文字入口',[311,y+12,477,y+66],'text_button')
    c.add('daily','arena_rank_marker','竞技场段位大标志',[1196,159,1460,330],'page_marker')
    c.add('daily','reward','段位奖励按钮',[1415,334,1475,373],'button',reuse=('arena','reward'))
    c.add('daily','reward_silver_many','大量月之印奖励',[1321,607,1392,677],
          'reward_icon',reuse=('activities','reward_silver_many'))
    c.add('daily','completed_stamp','已完成角标',[1031,514,1097,562],'page_marker')

    for i,(aid,label,box) in enumerate([
      ('tab_online','在线礼包',[277,214,539,318]),
      ('tab_daily','每日福利',[346,321,548,386]),
      ('tab_fund','等级基金',[347,388,554,450]),
      ('tab_level','等级礼包',[350,452,558,514]),
      ('tab_power','战斗力礼包',[351,516,560,578]),
      ('tab_recovery','资源追回',[353,580,562,642]),
    ]):c.add('welfare',aid,label,box,'button','选中' if i==0 else '未选中')
    c.add('welfare','close_panel','福利大厅关闭',[1572,102,1628,160],
          'button',reuse=('ranked','close_panel'))
    c.add('welfare','claim','领取按钮',[649,735,806,790],'button','可见，未操作')
    for i,box in enumerate(([942,735,1100,790],[1238,735,1396,790]),2):
        c.add('welfare',f'claim_{i}','领取按钮'+str(i),box,'button',
              '可见，未操作',reuse=('welfare','claim'))
    for aid,label,box in [
      ('reward_coin','铜币奖励',[657,553,712,604]),
      ('reward_book','书本奖励（物品名称未确认）',[736,558,795,605]),
      ('reward_ramen','拉面奖励',[653,640,706,704]),
      ('reward_megaphone','喇叭奖励',[737,638,790,704]),
      ('reward_scroll','卷轴奖励',[1037,551,1090,617]),
      ('reward_food','烤肉奖励（物品名称未确认）',[953,639,1013,703]),
      ('reward_potion','奔跑忍者图标奖励（物品名称未确认）',[1037,638,1091,701]),
      ('reward_dango','团子奖励（保留原数量2角标）',[1332,550,1405,623]),
      ('reward_coupon','点券奖励',[1254,640,1318,690]),
      ('reward_water','蓝色药水奖励（物品名称未确认）',[1341,639,1389,705]),
    ]:c.add('welfare',aid,label,box,'reward_icon')
    for i,(label,box) in enumerate([
      ('在线满10分钟可领取标记',[555,455,655,675]),
      ('在线满30分钟可领取标记',[850,455,950,675]),
      ('在线满60分钟可领取标记',[1145,455,1245,675]),
    ],1):c.add('welfare',f'claim_state_{i}',label,box,'page_marker')

    # Exact single-character boxes avoid connected serif neighbours. The family
    # is complete; subsequent identical digits are referenced, never recropped.
    for char,box in [
      ('1',[976,215,984,230]),('0',[984,215,993,230]),
      ('6',[993,215,1002,230]),('4',[1002,215,1012,230]),
      ('5',[1012,215,1021,230]),('2',[1030,215,1038,230]),
      ('9',[1038,215,1048,230]),('7',[1002,314,1012,329]),
      ('8',[975,413,984,428]),('3',[993,413,1003,428]),
    ]:c.digit('ranked','white_serif_small',char,box)
    c.red_digits('ranked',(172,85,388,142),'572798','ranked_red')
    c.red_digits('home',(223,80,413,121),'592897','home_red')
    # Activity large gold totals: split the separator too, but do not save it
    # as a digit, and reuse repeated digits across both visible totals.
    for origin,text,spans in [
      ((838,940),'35830/77600',[(10,9,24,35),(29,9,45,35),(51,9,66,35),(73,9,87,35),(92,9,108,35),(113,3,137,42),(142,10,158,35),(163,10,179,35),(184,9,200,36),(205,9,222,35),(226,9,243,35)]),
      ((394,940),'0/6950',[(5,9,21,35),(26,3,50,42),(55,9,71,36),(78,9,92,35),(98,9,114,35),(118,9,135,35)]),
    ]:
        for i,(char,box) in enumerate(zip(text,spans)):
            if char=='/':continue
            x,y,r,b=box;ox,oy=origin
            c.digit('daily','activity_gold_large',char,[ox+x,oy+y,ox+r,oy+b],
                    occurrence={'text':text,'index':i})
    # Action numbers and threshold badges are separate artwork/font families.
    for char,box in [('1',[693,30,721,82]),('2',[685,188,721,240]),
                     ('3',[504,85,538,137]),('4',[466,294,503,343])]:
        c.digit('arena','action_red',char,box)
    c.finish()


if __name__=='__main__':
    main()
