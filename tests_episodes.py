"""In-process episodes for every task: tools work, bad calls cost a call, the reference answer
scores 1 through submit, wrong/empty answers and the finish action score 0, budget exhaustion ends at 0."""
import json, sys
sys.path.insert(0, '.')
from shiftdesk.server.environment import DeskEnvironment
from shiftdesk.models import DeskAction
from shiftdesk.families import task_ids

bad = 0
for tid in task_ids():
    e = DeskEnvironment(allow_seed=True)
    o = e.reset(seed=7, task_id=tid)
    b = e._ep['built']
    assert o.calls_left == b.budget and not o.done and len(o.output) < 3000, (tid, len(o.output))
    for name in ('list_files', 'read_file', 'run_python', 'submit'):
        assert name in o.output
    o = e.step(DeskAction(tool='list_files', args={}))
    assert o.ok and all(f in o.output for f in b.files)
    if b.files:
        o = e.step(DeskAction(tool='read_file', args={'path': sorted(b.files)[0]}))
        assert o.ok and not o.done
    o = e.step(DeskAction(tool='run_python', args={'code': "import os\nprint(sorted(os.listdir()))"}))
    assert o.ok and not o.done, o.output
    o = e.step(DeskAction(tool='end_episode', args={}))
    assert not o.ok and not o.done
    o = e.step(DeskAction(tool='submit', args={'answer': b.answer}))
    good = o.done and o.reward == 1.0
    # answer passed as a JSON string
    e.reset(seed=7, task_id=tid)
    o2 = e.step(DeskAction(tool='submit', args={'answer': json.dumps(b.answer) if not isinstance(b.answer, str) else b.answer}))
    # finish action (empty answer) and a wrong answer
    e.reset(seed=7, task_id=tid)
    o3 = e.step(DeskAction(tool='submit', args={'answer': ''}))
    e.reset(seed=7, task_id=tid)
    o4 = e.step(DeskAction(tool='submit', args={'answer': b.wrong[0]})) if b.wrong and b.wrong[0] != b.answer else None
    # budget exhaustion
    e.reset(seed=7, task_id=tid)
    for _ in range(b.budget):
        o5 = e.step(DeskAction(tool='list_files', args={}))
    ok = (good and o2.reward == 1.0 and o3.done and o3.reward == 0.0 and (o4 is None or (o4.done and o4.reward == 0.0))
          and o5.done and o5.reward == 0.0)
    bad += not ok
    print(f"{tid:24s} ref={o.reward} json={o2.reward} finish={o3.reward} wrong={o4.reward if o4 else '-'} budget_end={o5.done},{o5.reward}")
print('EPISODES BAD', bad)
sys.exit(1 if bad else 0)
