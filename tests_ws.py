"""Play every task over the WebSocket protocol the way the arena does: example action ends it in [0,1]."""
import sys
from openenv.core.generic_client import GenericEnvClient
sys.path.insert(0, '.')
from shiftdesk.families import task_ids

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
bad = 0
for tid in task_ids():
    env = GenericEnvClient(base_url=url).sync()
    with env:
        r = env.reset(task_id=tid)
        assert tid in str(r.observation.get("task_id")), r
        assert len(r.observation.get("output", "")) > 50
        r = env.step({"tool": "nonexistent_tool", "args": {}})
        assert not r.done and r.observation.get("ok") is False
        r = env.step({"tool": "end_episode", "args": {}})
        ok = r.done and r.reward is not None and 0.0 <= float(r.reward) <= 1.0
        bad += not ok
        print(tid, "done", r.done, "reward", r.reward)
print("WS BAD", bad)
sys.exit(1 if bad else 0)
