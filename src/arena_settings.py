"""Arena-only settings shared by validation and the bounded battle loop."""
import re

DEFAULT_BATTLE_LIMIT=3


def battle_limit(cfg):
    value=cfg.get('arenaBattleLimit',DEFAULT_BATTLE_LIMIT)
    if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=100:
        raise ValueError('竞技场战斗场数上限应为1至100的整数')
    return value


def parse_battle_limit(text,*,enabled=True):
    # A text variable avoids Tk IntVar silently truncating decimal input.
    count=int(text.strip()) if isinstance(text,str) and re.fullmatch(r'[0-9]{1,3}',text.strip()) else 0
    if not enabled and not 1<=count<=100:return DEFAULT_BATTLE_LIMIT
    return battle_limit({'arenaBattleLimit':count})
