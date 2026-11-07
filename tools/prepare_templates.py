from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
TEMP=Path('C:/Users/lenovo/AppData/Local/Temp')
out=ROOT/'resources/local/image';out.mkdir(parents=True,exist_ok=True)
templates={
 'auto_on':('94847a0b-926e-48e0-b616-2ec5866061d8',(22,39,109,124)),
 'auto_off':('6f0e1624-1e91-40bc-9ffc-b3714a100fd0',(31,47,112,127)),
 'speed2':('94847a0b-926e-48e0-b616-2ec5866061d8',(120,88,162,131)),
 'start_battle':('fd027d49-8936-4f0a-b3bc-a1ea32a2f6b5',None),
 'end_battle':('5e1ca5b3-69ff-411d-b3b6-e57048f06cd9',(60,86,177,194)),
 'computer':('d2082d10-b7d0-4067-8c60-ef468152d171',(0,8,46,51)),
 'escort_SS':('20659741-e5d1-4d86-8a0a-5f1396c63ce9',(154,108,242,213)),
 'escort_S':('20659741-e5d1-4d86-8a0a-5f1396c63ce9',(165,292,238,388)),
 'victory':('9f37809e-fe0f-45ee-9093-df62e6ce2045',(244,90,460,270)),
 'strong_sky':('b6f7f557-58de-4d18-bef0-a6600fc61f5e',(216,253,374,339)),
 'strong_yaksha':('b6f7f557-58de-4d18-bef0-a6600fc61f5e',(575,250,746,338)),
 'strong_asura':('b6f7f557-58de-4d18-bef0-a6600fc61f5e',(921,253,1184,340)),
}
for name,(identifier,box) in templates.items():
    image=Image.open(TEMP/f'codex-clipboard-{identifier}.png').convert('RGB')
    if box:image=image.crop(box)
    for scale in (.65,.8,1,1.2,1.4):
        image.resize((round(image.width*scale),round(image.height*scale))).save(out/f'{name}_{scale}.png')
claimed=Image.open(ROOT/'verification/direct-native-click-after.png').convert('RGB').crop((369,833,414,877))
for scale in (.8,1,1.2):claimed.resize((round(claimed.width*scale),round(claimed.height*scale))).save(out/f'claimed_{scale}.png')
close=Image.open(ROOT/'verification/direct-native-click-after.png').convert('RGB').crop((1836,124,1882,174))
for scale in (.8,1,1.2):close.resize((round(close.width*scale),round(close.height*scale))).save(out/f'close_{scale}.png')
main=ROOT/'resources/local/main-calibration.png'
if not main.exists():Image.open(ROOT/'verification/background-latest.png').save(main)
for name,box in [('entry_survival',(992,114,1062,173)),('entry_strong',(1180,113,1242,174)),('entry_ranked',(1453,11,1514,69))]:
    icon=Image.open(main).convert('RGB').crop(box)
    for scale in (.8,1,1.2):icon.resize((round(icon.width*scale),round(icon.height*scale))).save(out/f'{name}_{scale}.png')
panel=ROOT/'resources/local/survival-calibration.png'
if not panel.exists() and (ROOT/'verification/native-integrated-panel.png').exists():
    Image.open(ROOT/'verification/native-integrated-panel.png').save(panel)
if panel.exists():
    pic=Image.open(panel).convert('RGB')
    pic.crop((962,901,1150,944)).save(out/'survival_reset1_verified.png')
    for label,x,y,variant in [(0,798,30,'ss'),(0,1300,174,'s'),(2,697,337,'a'),(3,1175,459,'b'),(5,1090,641,'c')]:
        pic.crop((x,y,x+21,y+24)).resize((84,96)).save(out/f'digit_{label}_{variant}.png')
reset_panel=ROOT/'resources/local/survival-reset-calibration.png'
if reset_panel.exists():
    pic=Image.open(reset_panel).convert('RGB')
    pic.crop((962,901,1150,944)).save(out/'survival_reset0_verified.png')
    pic.crop((798,30,819,54)).resize((84,96)).save(out/'digit_1_ss.png')
panel1920=ROOT/'resources/local/survival-1920-calibration.png'
if panel1920.exists():
    pic=Image.open(panel1920).convert('RGB')
    for value,grade,x,y in [(0,'ss',810,42),(2,'s',1308,190),(2,'a',710,357),(3,'b',1188,482),(5,'c',1105,658)]:
        pic.crop((x,y,x+21,y+24)).resize((84,96)).save(out/f'digit_{value}_1920_{grade}.png')
battle_panel=ROOT/'resources/local/battle-settlement-calibration.png'
if battle_panel.exists():
    pic=Image.open(battle_panel).convert('RGB')
    for name,box in [('speed1',(1437,942,1488,992)),('auto_on',(1340,902,1425,987)),('victory',(803,264,1106,550))]:
        pic.crop(box).save(out/f'{name}_verified.png')
reward_panel=ROOT/'resources/local/survival-reward-popup-calibration.png'
if reward_panel.exists():
    Image.open(reward_panel).crop((799,278,1140,375)).save(out/'reward_popup_verified.png')
reset1_panel=ROOT/'resources/local/survival-reset1-1920-calibration.png'
if reset1_panel.exists():
    Image.open(reset1_panel).crop((979,928,1157,973)).save(out/'survival_reset1_1920_verified.png')
