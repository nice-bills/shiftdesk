"""Run the policy's Python on a read-only copy of the task files.

The child drops to nobody when the server runs as root, gets CPU, memory,
file and process limits, and its whole process group is killed on timeout.
"""
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile

MAX_SOURCE_CHARS = 4000
MAX_OUTPUT_CHARS = 1500
WALL_TIMEOUT_S = 15
CPU_SECONDS = 8
MEMORY_BYTES = 768 * 1024 * 1024
NOBODY = 65534


def _limits() -> None:
    os.setsid()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 1))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    if os.geteuid() == 0:
        os.setgid(NOBODY)
        os.setuid(NOBODY)


def run_python(source: object, files: dict[str, str]) -> tuple[bool, str]:
    if isinstance(source, list) and all(isinstance(x, str) for x in source):
        source = "\n".join(source)
    if not isinstance(source, str) or not source.strip():
        return False, "the code argument must be a non-empty string of Python source"
    if len(source) > MAX_SOURCE_CHARS:
        return False, f"code is capped at {MAX_SOURCE_CHARS} characters"
    root = tempfile.mkdtemp(prefix="sd-")
    try:
        os.chmod(root, 0o755)
        for name, content in files.items():
            target = os.path.join(root, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.chmod(target, 0o444)
        for dirpath, dirnames, _ in os.walk(root):
            for d in dirnames:
                os.chmod(os.path.join(dirpath, d), 0o755)
        script = os.path.join(root, "_main.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(source + "\n")
        os.chmod(script, 0o444)
        proc = subprocess.Popen(
            [sys.executable, "-E", "-s", "-B", script],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            preexec_fn=_limits,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "PYTHONIOENCODING": "utf-8"},
        )
        try:
            out, _ = proc.communicate(timeout=WALL_TIMEOUT_S)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, _ = proc.communicate()
            timed_out = True
        text = out.decode("utf-8", "replace")
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS] + f"\n[output cut at {MAX_OUTPUT_CHARS} characters]"
        if timed_out:
            text += f"\n[killed after {WALL_TIMEOUT_S} s]"
        if not text.strip():
            text = "(no output; use print)"
        return True, text
    finally:
        shutil.rmtree(root, ignore_errors=True)
