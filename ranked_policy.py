"""Shared validation for ranked scope and the per-run attempt limit."""


def ranked_options(cfg):
    server=cfg.get('rankedServer','连服')
    if server=='联服':server='连服'
    if server not in ('本服','连服'):raise ValueError('排位战挑战范围应为本服或连服')
    limit=cfg.get('rankedLimit',0)
    if type(limit) is not int or not 0<=limit<=20:
        raise ValueError('排位战挑战上限应为0至20，0表示用完剩余次数')
    return server,limit
