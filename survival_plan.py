"""Shared survival plan validation and UI estimates (actual points come from game)."""
GRADES = ('SS', 'S', 'A', 'B', 'C')
POINTS = dict(zip(GRADES, (80, 60, 40, 30, 20)))
DEFAULT_COUNTS = dict(zip(GRADES, (1, 2, 2, 3, 5)))


def survival_plan(cfg):
    grades = cfg.get('survivalGrades', list(GRADES))
    if not isinstance(grades, list) or not grades or any(g not in GRADES for g in grades) or len(set(grades)) != len(grades):
        raise ValueError('生存演习请至少选择一个有效等级：SS、S、A、B、C')
    limits = cfg.get('survivalCounts')
    if limits is not None:
        if not isinstance(limits, dict) or any(type(limits.get(g)) is not int or not 1 <= limits[g] <= (1 if g == 'SS' else 30) for g in grades):
            raise ValueError('生存演习所选等级场数须为1至30；SS每天最多1场')
    return [g for g in GRADES if g in grades], limits


def estimate(cfg, initial=60, goal=220):
    grades, limits = survival_plan(cfg)
    if type(initial) is not int or type(goal) is not int or not 0 <= initial <= goal or goal <= 0:
        raise ValueError('积分估算起点应在0和目标之间，目标须大于0')
    counts = limits if limits is not None else DEFAULT_COUNTS
    added = sum(POINTS[g] * counts[g] for g in grades)
    return added, min(goal, initial + added), max(0, goal - initial - added)
