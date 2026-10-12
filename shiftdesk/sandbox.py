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


# Limits are set inside the child by this prelude (no preexec_fn: it can deadlock
# a threaded server between fork and exec). The user switch is done by Popen itself.
PRELUDE = (
    "import resource as r, runpy, sys\n"
    "r.setrlimit(r.RLIMIT_CORE, (0, 0))\n"
    f"r.setrlimit(r.RLIMIT_CPU, ({CPU_SECONDS}, {CPU_SECONDS + 1}))\n"
    f"r.setrlimit(r.RLIMIT_AS, ({MEMORY_BYTES}, {MEMORY_BYTES}))\n"
    "r.setrlimit(r.RLIMIT_FSIZE, (2097152, 2097152))\n"
    "r.setrlimit(r.RLIMIT_NPROC, (64, 64))\n"
    "sys.argv = [sys.argv[1]]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)


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
        drop = {"user": NOBODY, "group": NOBODY, "extra_groups": []} if os.geteuid() == 0 else {}
        proc = subprocess.Popen(
            [sys.executable, "-E", "-s", "-B", "-c", PRELUDE, script],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "PYTHONIOENCODING": "utf-8"},
            **drop,
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
        text = "\n".join(l for l in text.split("\n")
                         if not l.startswith(('  File "<string>"', '  File "<frozen runpy>"')))
        text = text.replace(root + "/", "")
        if not timed_out and proc.returncode is not None and proc.returncode < 0:
            text += f"\n[process killed by signal {-proc.returncode}: CPU or memory limit]"
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS] + f"\n[output cut at {MAX_OUTPUT_CHARS} characters]"
        if timed_out:
            text += f"\n[killed after {WALL_TIMEOUT_S} s]"
        if not text.strip():
            text = "(no output; use print)"
        return True, text
    finally:
        shutil.rmtree(root, ignore_errors=True)
