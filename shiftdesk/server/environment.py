"""ShiftDesk environment.

Each task is a family and a level. reset(task_id) builds a fresh instance of it.
Episodes that start within the same few minutes share one instance (seeded from a
secret baked into the image), so the parallel rollouts of one optimizer step are
compared on the same problem. Plain tools: list_files, read_file, write_file, bash,
run_python, submit. The episode keeps one working directory across calls. submit
ends the episode with an all-or-nothing reward; for file-deliverable tasks the
grader checks the file the policy wrote.
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
from ..sandbox import Workdir, reap_stale

BUCKET_S = 300
READ_CHARS = 2500
SALT_PATH = os.environ.get("SHIFTDESK_SALT", "/app/salt")
_PROCESS_SALT = secrets.token_hex(16)

TOOLS = ("list_files", "read_file", "write_file", "bash", "run_python", "submit")


def _salt():
    try:
        with open(SALT_PATH, encoding="utf-8") as fh:
            return fh.read().strip() or _PROCESS_SALT
    except OSError:
        return _PROCESS_SALT


class DeskEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, allow_seed: bool = False):
        super().__init__()
        self._allow_seed = allow_seed
        self._ep = None
        self._wd = None
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
        self._drop_workdir()
        reap_stale()
        self._wd = Workdir(built.files)
        self._ep = {"task_id": task_id, "built": built, "calls": 0, "done": False}
        self._state = State(episode_id=episode_id or str(uuid4()), step_count=0)
        return self._obs(self._reset_text(built), True, False, 0.0)

    def _reset_text(self, built):
        files = built.files
        listing = ", ".join(f"{n} ({self._size(c)})" for n, c in sorted(files.items())) or "none"
        first = sorted(files)[0] if files else "notes.txt"
        if built.deliverable:
            fmt = (f"Deliverable: write {built.deliverable} (relative to the working directory). Hidden checks "
                   f"grade that file when you submit (or when calls run out); the submit answer can be empty.")
        else:
            fmt = f"Answer format: {built.answer_hint}."
        return "\n".join([
            built.question,
            fmt,
            f"Files in the working directory: {listing}. Files you write stay there until the task ends.",
            "Tools (one call per reply):",
            '- list_files: list the working directory. {"tool": "list_files", "args": {}}',
            f"- read_file: show a file ({READ_CHARS} characters per call; optional \"offset\" = first line). "
            f'{{"tool": "read_file", "args": {{"path": "{first}"}}}}',
            '- write_file: create or overwrite a file. {"tool": "write_file", "args": {"path": "output/notes.txt", "content": "text"}}',
            '- bash: run a shell command (python3, grep, awk, sed, sort, jq, sqlite3, bc, openssl; everything needed is local). '
            f'{{"tool": "bash", "args": {{"command": "head -5 {first}"}}}}',
            "- run_python: run Python 3 (standard library, numpy, sympy, PIL) in the working directory; only printed output comes back. "
            '{"tool": "run_python", "args": {"code": "print(open(\'' + first + '\').read()[:200])"}}',
            '- submit: finish; this ends the task. {"tool": "submit", "args": {"answer": ' + ('""' if built.deliverable else '...') + '}}',
            f"You have {built.budget} calls in total, submit included.",
            "Reply with one JSON object and nothing else.",
        ])

    @staticmethod
    def _size(content):
        if isinstance(content, bytes):
            return f"{len(content)} bytes"
        return f"{len(content.splitlines())} lines"

    def _drop_workdir(self):
        if self._wd is not None:
            self._wd.cleanup()
            self._wd = None

    def close(self):
        self._drop_workdir()

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
        built = ep["built"]
        if tool == "submit":
            if "answer" in args:
                answer = args["answer"]
            elif args:
                answer = dict(args)  # the answer fields given directly as args
            else:
                answer = None
            try:
                if built.deliverable:
                    reward = self._grade_file(built)
                else:
                    reward = float(built.check(answer)) if answer not in (None, "") else 0.0
            except Exception:
                reward = 0.0
            return self._finish(max(0.0, min(1.0, reward)), "answer recorded")
        wd = self._wd
        if tool == "list_files":
            ok, out = True, wd.listing()
        elif tool == "read_file":
            ok, out = self._read(args)
        elif tool == "write_file":
            ok, out = wd.write_file(args.get("path"), args.get("content"))
        elif tool in ("bash", "shell", "run_bash"):
            cmd = args.get("command", args.get("cmd"))
            ok, out = wd.bash(cmd) if cmd is not None else (False, 'bash needs args.command, e.g. {"command": "ls -la"}')
        elif tool == "run_python":
            if "code" not in args:
                ok, out = False, "run_python needs args.code (a string of Python source)"
            else:
                ok, out = wd.run_python(args["code"])
        else:
            ok, out = False, f"unknown tool {tool!r}. Tools: {', '.join(TOOLS)}"
        left = built.budget - ep["calls"]
        if left <= 0:
            if built.deliverable:
                # like a test run at the end of a terminal task: whatever the deliverable holds now is graded
                return self._finish(self._grade_file(built), out + "\nno calls left; the task ended and the deliverable was graded")
            return self._finish(0.0, out + "\nno calls left; the task ended without an answer")
        return self._obs(out, ok, False, 0.0)

    def _grade_file(self, built):
        try:
            content = self._wd.grab(built.deliverable) if self._wd else None
            reward = float(built.check(content)) if content not in (None, "") else 0.0
        except Exception:
            reward = 0.0
        return max(0.0, min(1.0, reward))

    def _read(self, args):
        files = self._ep["built"].files
        path = args.get("path")
        if not isinstance(path, str):
            return False, f"read_file needs args.path, one of: {', '.join(sorted(files)) or 'no files'}"
        path = self._wd.rel(path) or path.strip()
        if path in files:
            content = files[path]
            if isinstance(content, bytes):
                return True, f"[binary file, {len(content)} bytes; inspect it with bash or run_python]"
        else:
            content = self._wd.read_text(path)
            if content is None:
                return False, f"no file {path!r}; task files: {', '.join(sorted(files)) or 'none'} (list_files shows everything)"
        lines = content.splitlines()
        try:
            start = max(1, int(args.get("offset", 1) or 1))
        except (TypeError, ValueError):
            start = 1
        out, used, i = [], 0, start - 1
        while i < len(lines) and used + len(lines[i]) + 1 <= READ_CHARS:
            out.append(lines[i])
            used += len(lines[i]) + 1
            i += 1
        text = "\n".join(out)
        if i < len(lines):
            text += f"\n[lines {start}-{i} of {len(lines)}; more with offset={i + 1}]"
        return True, text or "(empty)"

    def _finish(self, reward, out):
        self._ep["done"] = True
        self._drop_workdir()
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
