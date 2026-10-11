import sys, json; sys.path.insert(0,'.')
from shiftdesk.server.environment import DeskEnvironment
from shiftdesk.models import DeskAction
from shiftdesk.families import task_ids
for tid in task_ids():
    e = DeskEnvironment(allow_seed=True)
    o = e.reset(seed=7, task_id=tid)
    names = e._ep['names']; b = e._ep['built']
    o = e.step(DeskAction(tool=names['list'][0], args={}))
    f = sorted(b.files)[0] if b.files else None
    if f:
        o = e.step(DeskAction(tool=names['read'][0], args={names['read'][1][0]: f}))
    o = e.step(DeskAction(tool=names['python'][0], args={names['python'][1][0]: "import os\nprint(len(os.listdir()))\nprint(open('/etc/hostname').read()[:5])"}))
    py = o.output.strip().replace('\n',' | ')
    o = e.step(DeskAction(tool='bogus', args={}))
    assert not o.ok
    o = e.step(DeskAction(tool=names['submit'][0], args={names['submit'][1][0]: b.answer}))
    e2 = DeskEnvironment(); e2.reset(task_id=tid); o2 = e2.step(DeskAction(tool='end_episode', args={}))
    print(f"{tid:20s} reward={o.reward} done={o.done} end_ep={o2.done},{o2.reward} py=[{py[:60]}]")
