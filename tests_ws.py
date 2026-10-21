"""Play every task over the WebSocket protocol the way the arena does: the example/finish action
({"tool": "submit", "args": {"answer": ""}}) ends it with a reward in [0, 1]. Exercises every tool,
checks the workdir persists across calls, and probes the sandbox from the policy's side: the salt and the
server code are unreadable, nothing outside the workdir/tmp is writable, and (reported) whether the
network is reachable."""
import json
import sys
from openenv.core.generic_client import GenericEnvClient
sys.path.insert(0, '.')
from shiftdesk.families import parse_task_id, task_ids

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
bad = 0
probe_done = False
for tid in task_ids():
    env = GenericEnvClient(base_url=url).sync()
    with env:
        r = env.reset(task_id=tid)
        out = r.observation.get("output", "")
        assert tid in str(r.observation.get("task_id")), r
        assert len(out) > 50 and all(t in out for t in ("write_file", "bash", "run_python", "submit")), out
        r = env.step({"tool": "nonexistent_tool", "args": {}})
        assert not r.done and r.observation.get("ok") is False
        r = env.step({"tool": "list_files", "args": {}})
        assert not r.done and r.observation.get("ok") is True and "output" in r.observation.get("output", "")
        r = env.step({"tool": "run_python", "args": {"code": "import os\nprint('N', len(os.listdir()))\n"
                      "try:\n    open('/app/salt').read(); print('SALT READABLE')\nexcept OSError:\n    print('salt hidden')"}})
        out = r.observation.get("output", "")
        assert not r.done and "N " in out and "SALT READABLE" not in out, out
        r = env.step({"tool": "write_file", "args": {"path": "output/probe.txt", "content": "persist-me"}})
        assert not r.done and r.observation.get("ok") is True, r.observation
        r = env.step({"tool": "bash", "args": {"command": "cat output/probe.txt; echo; ls | head -3"}})
        out = r.observation.get("output", "")
        assert not r.done and "persist-me" in out, out
        if not probe_done:
            probe_done = True
            cmd = ("echo uid=$(id -u); cat /app/salt >/dev/null 2>&1 && echo SALT_READ; "
                   "ls /app/env >/dev/null 2>&1 && echo CODE_LISTED; cat /app/env/shiftdesk/server/environment.py >/dev/null 2>&1 && echo CODE_READ; "
                   "touch /app/pwn 2>/dev/null && echo WROTE_APP; touch /etc/pwn 2>/dev/null && echo WROTE_ETC; "
                   "ls /tmp/sdwork >/dev/null 2>&1 && echo LISTED_OTHER_EPISODES; "
                   "for t in jq sqlite3 bc openssl awk sed grep sort python3; do command -v $t >/dev/null || echo MISSING_$t; done; "
                   "python3 -c 'import sympy, numpy, PIL; print(\"libs ok\")'; "
                   "python3 -c 'import socket; s=socket.create_connection((\"1.1.1.1\", 53), timeout=3); print(\"NETWORK_REACHABLE\")' 2>/dev/null || echo network_blocked")
            r = env.step({"tool": "bash", "args": {"command": cmd}})
            out = r.observation.get("output", "")
            print("sandbox probe:", " | ".join(out.split("\n")))
            for flag in ("SALT_READ", "CODE_LISTED", "CODE_READ", "WROTE_APP", "WROTE_ETC", "LISTED_OTHER_EPISODES", "MISSING_",
                         "NETWORK_REACHABLE"):
                if flag in out and not (flag == "LISTED_OTHER_EPISODES" and "uid=65534" not in out):
                    print("SANDBOX FAIL", flag)
                    bad += 1
            assert "libs ok" in out, out
            # a symlinked deliverable pointing at the salt must not crash grading or leak
            r = env.step({"tool": "bash", "args": {"command": "ln -sf /app/salt output/answer.json; ls -l output"}})
            assert not r.done
        r = env.step({"tool": "submit", "args": {"answer": ""}})
        ok = r.done and r.reward is not None and 0.0 <= float(r.reward) <= 1.0
        bad += not ok
        print(tid, "done", r.done, "reward", r.reward)
print("WS BAD", bad)
sys.exit(1 if bad else 0)
