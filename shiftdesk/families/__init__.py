from . import fin, ind, math_, med, off, sci, sec, sw

FAMILIES = {m.NAME: m for m in (sw, ind, sci, off, fin, math_, sec, med)}
LEVELS = (1, 2, 3)


def task_ids():
    return [f"{name}-L{level}" for name in FAMILIES for level in LEVELS]


def parse_task_id(task_id):
    if not isinstance(task_id, str) or "-L" not in task_id:
        raise ValueError(f"unknown task_id: {task_id!r}")
    name, level = task_id.rsplit("-L", 1)
    if name not in FAMILIES or level not in ("1", "2", "3"):
        raise ValueError(f"unknown task_id: {task_id!r}")
    return FAMILIES[name], int(level)
