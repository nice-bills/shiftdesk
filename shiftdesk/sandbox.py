"""Per-episode sandbox: a working directory that persists across tool calls.

Each episode gets one directory holding the task files plus an empty output/
folder. run_python and bash run inside it as nobody (when the server runs as
root), with CPU, memory, file-size and process limits, a wall timeout that
kills the whole process group, and no network when the kernel allows a fresh
network namespace. write_file writes through the same sandboxed child, so a
symlink planted by the policy can never make the server write as root.
The grader reads deliverables with O_NOFOLLOW and only inside the workdir.
"""
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

MAX_SOURCE_CHARS = 6000
MAX_WRITE_CHARS = 60000
MAX_OUTPUT_CHARS = 1500
WALL_TIMEOUT_S = 20
CPU_SECONDS = 10
MEMORY_BYTES = 1024 * 1024 * 1024
FILE_BYTES = 4 * 1024 * 1024
MAX_PROCS = 128
NOBODY = 65534
STALE_S = 2 * 3600
IS_ROOT = os.geteuid() == 0
BASE = os.environ.get("SHIFTDESK_WORK_BASE", os.path.join(tempfile.gettempdir(), "sdwork"))
SCRIPTS = os.path.join(tempfile.gettempdir(), "sdscripts")

# Limits are set inside the child by this prelude (no preexec_fn: it can deadlock
# a threaded server between fork and exec). argv: [prelude, mode, payload].
# No network without privileges: a seccomp filter (inherited across exec) makes socket(AF_INET/AF_INET6)
# fail with EACCES. Unix sockets still work. If the kernel refuses the filter, the child runs without it.
NO_NET = r"""
def _nonet():
    import ctypes, platform, struct
    arch = {"x86_64": (0xC000003E, (41, 0x40000000 | 41)), "aarch64": (0xC00000B7, (198,))}.get(platform.machine())
    if not arch:
        return False
    A, nrs = arch
    n = len(nrs)
    allow, deny = 6 + n, 7 + n
    ins = [(0x20, 0, 0, 4), (0x15, 0, allow - 2, A), (0x20, 0, 0, 0)]
    for j, nr in enumerate(nrs):
        i = 3 + j
        ins.append((0x15, (3 + n) - (i + 1), 0 if j < n - 1 else allow - (i + 1), nr))
    ins += [(0x20, 0, 0, 16), (0x15, deny - (5 + n), 0, 2), (0x15, deny - (6 + n), 0, 10),
            (0x06, 0, 0, 0x7FFF0000), (0x06, 0, 0, 0x00050000 | 13)]
    code = b"".join(struct.pack("=HBBI", *x) for x in ins)
    keep = ctypes.create_string_buffer(code, len(code))
    prog = ctypes.create_string_buffer(struct.pack("=HxxxxxxQ", len(ins), ctypes.addressof(keep)), 16)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        return False
    return libc.prctl(22, 2, ctypes.addressof(prog), 0, 0) == 0
try:
    _nonet()
except Exception:
    pass
"""

PRELUDE = (
    "import os, resource as r, runpy, sys\n"
    + NO_NET +
    "r.setrlimit(r.RLIMIT_CORE, (0, 0))\n"
    f"r.setrlimit(r.RLIMIT_CPU, ({CPU_SECONDS}, {CPU_SECONDS + 1}))\n"
    f"r.setrlimit(r.RLIMIT_AS, ({MEMORY_BYTES}, {MEMORY_BYTES}))\n"
    f"r.setrlimit(r.RLIMIT_FSIZE, ({FILE_BYTES}, {FILE_BYTES}))\n"
    f"r.setrlimit(r.RLIMIT_NPROC, ({MAX_PROCS}, {MAX_PROCS}))\n"
    "mode, payload = sys.argv[1], sys.argv[2]\n"
    "if mode == 'bash':\n"
    "    os.execve('/bin/bash', ['bash', '-c', payload], os.environ)\n"
    "elif mode == 'write':\n"
    "    p = os.path.normpath(payload)\n"
    "    if p.startswith('..') or os.path.isabs(p):\n"
    "        print('path must stay inside the working directory'); sys.exit(2)\n"
    "    d = os.path.dirname(p)\n"
    "    if d: os.makedirs(d, exist_ok=True)\n"
    "    data = sys.stdin.buffer.read()\n"
    "    with open(p, 'wb') as fh: fh.write(data)\n"
    "    print(f'wrote {len(data)} bytes to {p}')\n"
    "elif mode == 'read':\n"
    "    p = os.path.normpath(payload)\n"
    "    with open(p, 'rb') as fh: sys.stdout.buffer.write(fh.read(200000))\n"
    "else:\n"
    "    sys.argv = [payload]\n"
    "    runpy.run_path(payload, run_name='__main__')\n"
)

_NETNS = None
# The server's own interpreter first (it is /usr/local/bin in the image), then the system dirs.
PATH = ":".join(dict.fromkeys(
    [p for p in os.environ.get("SHIFTDESK_EXTRA_PATH", "").split(":") if p]
    + [os.path.dirname(sys.executable), "/usr/local/bin", "/usr/bin", "/bin"]))


def _netns_prefix():
    """Probe once whether children can get an empty network namespace."""
    global _NETNS
    if _NETNS is not None:
        return _NETNS
    _NETNS = []
    unshare, setpriv = shutil.which("unshare"), shutil.which("setpriv")
    candidates = []
    if IS_ROOT and unshare and setpriv:
        candidates.append([unshare, "--net", "--", setpriv, f"--reuid={NOBODY}", f"--regid={NOBODY}", "--clear-groups", "--"])
    for pre in candidates:
        try:
            r = subprocess.run(pre + [sys.executable, "-c", "import socket,os;print(os.geteuid())"],
                               capture_output=True, timeout=10)
            if r.returncode == 0 and (not IS_ROOT or r.stdout.strip() == str(NOBODY).encode()):
                _NETNS = pre
                break
        except Exception:
            pass
    return _NETNS


def network_isolated() -> bool:
    return bool(_netns_prefix())


def _secure_dir(path, mode):
    os.makedirs(path, exist_ok=True)
    if IS_ROOT:
        os.chown(path, 0, 0)
    os.chmod(path, mode)


def reap_stale(now=None):
    now = now or time.time()
    try:
        names = os.listdir(BASE)
    except OSError:
        return
    for name in names:
        p = os.path.join(BASE, name)
        try:
            if now - os.lstat(p).st_mtime > STALE_S:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


class Workdir:
    """One episode's working directory."""

    def __init__(self, files: dict):
        # The parent is root-owned and not listable, so one episode cannot find another's directory.
        _secure_dir(BASE, 0o711)
        _secure_dir(SCRIPTS, 0o711)
        self.root = tempfile.mkdtemp(prefix="ep-", dir=BASE)
        for name, content in files.items():
            target = os.path.join(self.root, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            mode = "wb" if isinstance(content, bytes) else "w"
            with open(target, mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as fh:
                fh.write(content)
        os.makedirs(os.path.join(self.root, "output"), exist_ok=True)
        for dirpath, dirnames, filenames in os.walk(self.root):
            for n in dirnames + filenames:
                p = os.path.join(dirpath, n)
                os.chmod(p, 0o755 if os.path.isdir(p) else 0o644)
                if IS_ROOT:
                    os.chown(p, NOBODY, NOBODY)
        os.chmod(self.root, 0o755)
        if IS_ROOT:
            os.chown(self.root, NOBODY, NOBODY)

    # ---- running things
    def _run(self, mode, payload, stdin_bytes=None):
        env = {"PATH": PATH, "HOME": self.root, "LANG": "C.UTF-8",
               "PYTHONIOENCODING": "utf-8", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
               "PYTHONDONTWRITEBYTECODE": "1", "TERM": "dumb"}
        argv = [sys.executable, "-E", "-s", "-B", "-c", PRELUDE, mode, payload]
        pre = _netns_prefix()
        drop = {}
        if pre:
            argv = pre + argv
        elif IS_ROOT:
            drop = {"user": NOBODY, "group": NOBODY, "extra_groups": []}
        proc = subprocess.Popen(
            argv, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
            start_new_session=True, env=env, **drop,
        )
        try:
            out, _ = proc.communicate(input=stdin_bytes, timeout=WALL_TIMEOUT_S)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, _ = proc.communicate()
            timed_out = True
        return proc.returncode, out, timed_out

    def _clean(self, out, rc, timed_out, cut=True):
        text = out.decode("utf-8", "replace")
        text = "\n".join(l for l in text.split("\n")
                         if not l.startswith(('  File "<string>"', '  File "<frozen runpy>"')))
        text = text.replace(self.root + "/", "").replace(self.root, ".")
        if not timed_out and rc is not None and rc < 0:
            text += f"\n[process killed by signal {-rc}: CPU or memory limit]"
        if cut and len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS] + f"\n[output cut at {MAX_OUTPUT_CHARS} characters]"
        if timed_out:
            text += f"\n[killed after {WALL_TIMEOUT_S} s]"
        return text

    def run_python(self, source):
        if isinstance(source, list) and all(isinstance(x, str) for x in source):
            source = "\n".join(source)
        if not isinstance(source, str) or not source.strip():
            return False, "the code argument must be a non-empty string of Python source"
        if len(source) > MAX_SOURCE_CHARS:
            return False, f"code is capped at {MAX_SOURCE_CHARS} characters"
        fd, script = tempfile.mkstemp(prefix="s-", suffix=".py", dir=SCRIPTS)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(source + "\n")
            os.chmod(script, 0o444)
            rc, out, to = self._run("py", script)
            text = self._clean(out, rc, to).replace(script, "main.py")
            if rc not in (0, None) and not text.strip():
                text = f"(exit status {rc}, no output)"
            return True, text if text.strip() else "(no output; use print)"
        finally:
            try:
                os.unlink(script)
            except OSError:
                pass

    def bash(self, command):
        if not isinstance(command, str) or not command.strip():
            return False, "bash needs args.command, a non-empty shell command string"
        if len(command) > MAX_SOURCE_CHARS:
            return False, f"command is capped at {MAX_SOURCE_CHARS} characters"
        rc, out, to = self._run("bash", command)
        text = self._clean(out, rc, to)
        if rc not in (0, None) and rc > 0:
            text = (text.rstrip("\n") + "\n" if text.strip() else "") + f"[exit status {rc}]"
        return True, text if text.strip() else "(no output, exit status 0)"

    def write_file(self, path, content):
        if not isinstance(path, str) or not path.strip():
            return False, "write_file needs args.path (relative to the working directory) and args.content"
        if not isinstance(content, str):
            return False, "write_file needs args.content as a string"
        if len(content) > MAX_WRITE_CHARS:
            return False, f"content is capped at {MAX_WRITE_CHARS} characters"
        path = self.rel(path)
        if path is None:
            return False, "path must stay inside the working directory"
        rc, out, to = self._run("write", path, content.encode("utf-8"))
        return rc == 0, self._clean(out, rc, to).strip() or f"exit status {rc}"

    def read_text(self, path):
        """Read a file the policy created, as the policy would (sandboxed)."""
        rel = self.rel(path)
        if rel is None:
            return None
        rc, out, to = self._run("read", rel)
        if rc != 0:
            return None
        return out.decode("utf-8", "replace")

    def rel(self, path):
        path = path.strip()
        if path.startswith(self.root):
            path = path[len(self.root):]
        for pre in ("/work/", "./"):
            if path.startswith(pre):
                path = path[len(pre):]
        p = os.path.normpath(path)
        if os.path.isabs(p) or p == ".." or p.startswith("../"):
            return None
        return p

    def listing(self):
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            rel = os.path.relpath(dirpath, self.root)
            for n in sorted(filenames):
                p = os.path.join(dirpath, n)
                try:
                    size = os.lstat(p).st_size
                except OSError:
                    continue
                out.append(f"{n if rel == '.' else os.path.join(rel, n)} ({size} bytes)")
            if rel != "." and not filenames and not dirnames:
                out.append(rel + "/ (empty)")
            if len(out) > 200:
                out.append("[listing cut]")
                break
        if not any(x.startswith("output/") for x in out):
            out.append("output/ (empty)")
        return "\n".join(out)

    def grab(self, rel, limit=1_000_000):
        """Read a deliverable for grading: regular file inside the workdir, no symlinks anywhere on the path."""
        p = os.path.normpath(rel)
        if os.path.isabs(p) or p.startswith(".."):
            return None
        cur = self.root
        parts = p.split(os.sep)
        try:
            for part in parts[:-1]:
                cur = os.path.join(cur, part)
                if not stat.S_ISDIR(os.lstat(cur).st_mode):
                    return None
            fd = os.open(os.path.join(cur, parts[-1]), os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0))
        except OSError:
            return None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            data = os.read(fd, limit + 1)
            if len(data) > limit:
                return None
            return data.decode("utf-8", "replace")
        finally:
            os.close(fd)

    def cleanup(self):
        if self.root and os.path.isdir(self.root):
            shutil.rmtree(self.root, ignore_errors=True)
        self.root = None


def run_python(source: object, files: dict) -> tuple:
    """v3 compatibility: one-off run in a throwaway workdir."""
    w = Workdir(files)
    try:
        return w.run_python(source)
    finally:
        w.cleanup()
