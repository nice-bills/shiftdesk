"""ShiftDesk environment.

Each task is a family and a level. reset(task_id) builds a fresh instance of it.
Episodes that start within the same few minutes share one instance (seeded from a
secret baked into the image), so the parallel rollouts of one optimizer step are
compared on the same problem. Tool names and argument names are drawn per
instance too and listed in the reset text.
"""
import hashlib
import json
import os
import random
import secrets
import time
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from ..families import parse_task_id
from ..models import DeskAction, DeskObservation
from ..sandbox import run_python

BUCKET_S = 300
READ_CHARS = 2500
SALT_PATH = os.environ.get("SHIFTDESK_SALT", "/app/salt")
_PROCESS_SALT = secrets.token_hex(16)

ALIASES = {
    "list": (["ls", "list_files", "dir", "files"], []),
    "read": (["read", "cat", "open_file", "view_file"], [["path", "file", "filename"], ["offset", "start_line", "from_line"]]),
    "python": (["python", "run_python", "py", "exec_code", "sandbox"], [["code", "source", "script", "program"]]),
    "submit": (["submit", "final_answer", "answer", "report", "submit_answer"], [["answer", "value", "result", "final"]]),
}
HIDDEN_END = "end_episode"  # used only by the arena's admission replay and finish_action


def _salt():
    try:
        with open(SALT_PATH, encoding="utf-8") as fh:
            return fh.read().strip() or _PROCESS_SALT
    except OSError:
        return _PROCESS_SALT


def _example(tool, argnames, values):
    return json.dumps({"tool": tool, "args": dict(zip(argnames, values))})


class DeskEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, allow_seed: bool = False):
        super().__init__()
        self._allow_seed = allow_seed
        self._ep = None
        self._state = State(episode_id=None, step_count=0)

    # ---- episode setup
    def reset(self, seed=None, episode_id=None, task_id=None, **kwargs) -> DeskObservation:
        family, level = parse_task_id(task_id)
        if seed is not None and self._allow_seed:
            rng_seed = f"seed:{seed}"
        else:
            rng_seed = f"{_salt()}|{task_id}|{int(time.time() // BUCKET_S)}"
        rng = random.Random(int(hashlib.sha256(rng_seed.encode()).hexdigest(), 16))
        built = family.build(level, rng)
        names = {}
        for role, (tools, argsets) in ALIASES.items():
            names[role] = (rng.choice(tools), [rng.choice(a) for a in argsets])
        hint_style = rng.random()
        self._ep = {"task_id": task_id, "built": built, "names": names, "calls": 0, "done": False}
        self._state = State(episode_id=episode_id or str(uuid4()), step_count=0)
        return self._obs(self._reset_text(built, names, hint_style), True, False, 0.0)

    def _reset_text(self, built, names, hint_style):
        files = built.files
        if files:
            listing = ", ".join(f"{n} ({len(c.splitlines())} lines)" for n, c in sorted(files.items()))
        else:
            listing = "none"
        lt, _ = names["list"]
        rt, (rp, ro) = names["read"]
        pt, (pc,) = names["python"]
        st, (sa,) = names["submit"]
        first = sorted(files)[0] if files else "notes.txt"
        tools = [
            f"- {lt}: list the task files. {_example(lt, [], [])}",
            f"- {rt}: show a file, {READ_CHARS} characters at most per call; '{ro}' is an optional first line number. "
            f"{_example(rt, [rp], [first])}",
            f"- {pt}: run Python 3 (standard library) with the task files in the working directory (read-only; "
            f"write scratch files under /tmp). Only printed output comes back. "
            f"{_example(pt, [pc], ['import os' + chr(10) + 'print(sorted(os.listdir()))'])}",
            f"- {st}: give the final answer and end the task. {_example(st, [sa], ['...'])}",
        ]
        text = [
            built.question,
            f"Answer format: {built.answer_hint}.",
            f"Files: {listing}.",
            "Tools (call exactly one per reply):",
            *tools,
            f"You have {built.budget} calls in total, the final answer included.",
        ]
        if hint_style < 0.5:
            text.append('Reply with one JSON object and nothing else, e.g. {"tool": "...", "args": {...}}.')
        return "\n".join(text)

    # ---- steps
    def step(self, action: DeskAction, timeout_s=None, **kwargs) -> DeskObservation:
        ep = self._ep
        if ep is None:
            raise RuntimeError("call reset(task_id=...) first")
        if ep["done"]:
            return self._obs("the task is over", False, True, 0.0)
        ep["calls"] += 1
        self._state = State(episode_id=self._state.episode_id, step_count=ep["calls"])
        tool = (action.tool or "").strip()
        args = action.args if isinstance(action.args, dict) else {}
        names = ep["names"]
        built = ep["built"]
        if tool == HIDDEN_END:
            return self._finish(0.0, "ended")
        if tool == names["submit"][0]:
            key = names["submit"][1][0]
            if key not in args:
                ok, out = False, f"{tool} needs args.{key}"
            else:
                try:
                    reward = float(built.check(args[key]))
                except Exception:
                    reward = 0.0
                return self._finish(max(0.0, min(1.0, reward)), "answer recorded")
        elif tool == names["list"][0]:
            ok, out = True, "\n".join(sorted(built.files)) or "(no files)"
        elif tool == names["read"][0]:
            ok, out = self._read(args, names["read"][1])
        elif tool == names["python"][0]:
            key = names["python"][1][0]
            if key not in args:
                ok, out = False, f"{tool} needs args.{key} (a string of Python source)"
            else:
                ok, out = run_python(args[key], built.files)
        else:
            valid = ", ".join(n for n, _ in names.values())
            ok, out = False, f"unknown tool {tool!r}. The tools for this task are: {valid}"
        left = built.budget - ep["calls"]
        if left <= 0:
            return self._finish(0.0, out + "\nno calls left; the task ended without an answer")
        return self._obs(out, ok, False, 0.0)

    def _read(self, args, argnames):
        pkey, okey = argnames
        files = self._ep["built"].files
        path = args.get(pkey)
        if not isinstance(path, str):
            return False, f"needs args.{pkey}, one of: {', '.join(sorted(files)) or 'no files'}"
        path = path.strip().lstrip("./")
        if path not in files:
            return False, f"no file {path!r}; files: {', '.join(sorted(files)) or 'none'}"
        lines = files[path].splitlines()
        try:
            start = max(1, int(args.get(okey, 1) or 1))
        except (TypeError, ValueError):
            start = 1
        out, used, i = [], 0, start - 1
        while i < len(lines) and used + len(lines[i]) + 1 <= READ_CHARS:
            out.append(lines[i])
            used += len(lines[i]) + 1
            i += 1
        text = "\n".join(out)
        if i < len(lines):
            text += f"\n[lines {start}-{i} of {len(lines)}; more with {okey}={i + 1}]"
        return True, text or "(empty)"

    def _finish(self, reward, out):
        self._ep["done"] = True
        return self._obs(out, True, True, reward)

    def _obs(self, out, ok, done, reward):
        ep = self._ep or {}
        budget = ep["built"].budget if ep else 0
        return DeskObservation(
            task_id=ep.get("task_id", ""),
            output=out,
            ok=ok,
            calls_left=max(budget - ep.get("calls", 0), 0),
            done=done,
            reward=reward,
        )

    @property
    def state(self) -> State:
        return self._state
