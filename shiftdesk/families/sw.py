"""Software: repair a small Python module; hidden tests grade the fixed file."""
import json

from ..sandbox import run_python
from .base import Built

DOMAIN = "software-engineering"
NAME = "module-repair"

# name: (source, [(buggy_from, buggy_to)], input generator code, doc)
TEMPLATES = {
    "median": (
        '''def median(xs):
    """Median of a non-empty list of numbers. Even length: mean of the two middle values.
    Raises ValueError on an empty list."""
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("empty")
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2
''',
        [("(s[mid - 1] + s[mid]) / 2", "(s[mid] + s[mid + 1]) / 2"), ("s = sorted(xs)", "s = list(xs)"),
         ("if n % 2 == 1:", "if n % 2 == 0:")],
        "lambda r: ([r.randint(-50, 50) for _ in range(r.randint(0, 9))],)",
    ),
    "merge_intervals": (
        '''def merge_intervals(items):
    """Merge overlapping or touching closed intervals given as (start, end) pairs.
    Returns sorted tuples; (1, 3) and (3, 5) merge into (1, 5)."""
    out = []
    for start, end in sorted(items):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [tuple(x) for x in out]
''',
        [("start <= out[-1][1]", "start < out[-1][1]"), ("max(out[-1][1], end)", "end"),
         ("for start, end in sorted(items):", "for start, end in items:")],
        "lambda r: ([tuple(sorted((r.randint(0, 30), r.randint(0, 30)))) for _ in range(r.randint(0, 7))],)",
    ),
    "parse_duration": (
        '''def parse_duration(text):
    """Seconds in a duration such as "1h30m", "45s" or "2h5s". Units h, m, s; each needs a number.
    Raises ValueError on anything else, including a trailing number without a unit."""
    total = 0
    num = ""
    units = {"h": 3600, "m": 60, "s": 1}
    for ch in text.strip():
        if ch.isdigit():
            num += ch
        elif ch in units and num:
            total += int(num) * units[ch]
            num = ""
        else:
            raise ValueError(text)
    if num:
        raise ValueError(text)
    return total
''',
        [('"m": 60', '"m": 100'), ("if num:\n        raise ValueError(text)", "if num:\n        total += int(num)"),
         ("total += int(num) * units[ch]", "total = int(num) * units[ch]")],
        "lambda r: (''.join(r.choice(['1','2','7','30','h','m','s','45','']) for _ in range(r.randint(1, 5))),)",
    ),
    "rle_encode": (
        '''def rle_encode(s):
    """Run-length encode: "aaabcc" -> "3a1b2c". Empty string -> ""."""
    if not s:
        return ""
    out = []
    prev, count = s[0], 1
    for ch in s[1:]:
        if ch == prev:
            count += 1
        else:
            out.append(f"{count}{prev}")
            prev, count = ch, 1
    out.append(f"{count}{prev}")
    return "".join(out)
''',
        [('    out.append(f"{count}{prev}")\n    return', "    return"), ("prev, count = ch, 1", "prev, count = ch, 0"),
         ("for ch in s[1:]:", "for ch in s[2:]:")],
        "lambda r: (''.join(r.choice('aab') for _ in range(r.randint(0, 9))),)",
    ),
    "top_k_words": (
        '''def top_k_words(text, k):
    """The k most frequent words, case-insensitive, punctuation .,!?;: stripped from word ends.
    Ties are broken alphabetically. Returns a list of at most k words."""
    counts = {}
    for word in text.lower().split():
        word = word.strip(".,!?;:")
        if word:
            counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:k]]
''',
        [("(-kv[1], kv[0])", "(kv[1], kv[0])"), ("for word in text.lower().split():", "for word in text.split():"),
         ("ranked[:k]", "ranked[:k - 1]")],
        "lambda r: (' '.join(r.choice(['Red','red','blue','Blue.','green!','red,','tea']) for _ in range(r.randint(0, 12))), r.randint(1, 4))",
    ),
    "chunk": (
        '''def chunk(xs, size):
    """Split a list into consecutive pieces of length size; the last piece may be shorter.
    Raises ValueError if size < 1."""
    if size <= 0:
        raise ValueError("size")
    return [xs[i:i + size] for i in range(0, len(xs), size)]
''',
        [("range(0, len(xs), size)", "range(0, len(xs) - size, size)"), ("xs[i:i + size]", "xs[i:i + size - 1]"),
         ("if size <= 0:", "if size <= 1:")],
        "lambda r: (list(range(r.randint(0, 11))), r.randint(0, 4))",
    ),
}

HARNESS = r'''
import json, random, sys
sys.path.insert(0, ".")
REF = {ref!r}
NAMES = {names!r}
GENS = {gens!r}
ns = {{}}
exec(REF, ns)
try:
    import solution
except Exception as e:
    print("RESULT 0 import failed:", type(e).__name__)
    sys.exit(0)
r = random.Random({seed})
for name in NAMES:
    gen = eval(GENS[name])
    fn = getattr(solution, name, None)
    if fn is None:
        print("RESULT 0 missing", name); sys.exit(0)
    for _ in range(150):
        args = gen(r)
        def run(f):
            try:
                return ("ok", f(*json.loads(json.dumps(args))))
            except ValueError:
                return ("ValueError", None)
            except Exception as e:
                return ("crash", type(e).__name__)
        want = run(ns[name])
        try:
            got = run(fn)
        except BaseException as e:
            got = ("crash", type(e).__name__)
        if want[0] == "ok" and got[0] == "ok":
            a, b = want[1], got[1]
            if isinstance(a, list):
                a = [tuple(x) if isinstance(x, list) else x for x in a]
            if isinstance(b, list):
                b = [tuple(x) if isinstance(x, list) else x for x in b]
            if a == b:
                continue
        elif want[0] == got[0] == "ValueError":
            continue
        print("RESULT 0 mismatch", name)
        sys.exit(0)
print("RESULT 1")
'''


def _differs(ref_src, bug_src, name, gen_src, rng):
    a, b = {}, {}
    exec(ref_src, a)
    exec(bug_src, b)
    gen = eval(gen_src)
    for _ in range(400):
        args = gen(rng)
        try:
            ra = ("ok", a[name](*args))
        except ValueError:
            ra = ("ValueError", None)
        try:
            rb = ("ok", b[name](*args))
        except ValueError:
            rb = ("ValueError", None)
        except Exception as e:
            rb = ("crash", type(e).__name__)
        if ra != rb:
            return args, ra
    return None


def build(level, rng):
    k = {1: 1, 2: 2, 3: 3}[level]
    names = rng.sample(sorted(TEMPLATES), k)
    ref_parts, bug_parts, tests = [], [], []
    for i, name in enumerate(names):
        src, bugs, gen = TEMPLATES[name]
        frm, to = rng.choice(bugs)
        bug = src.replace(frm, to, 1)
        ref_parts.append(src)
        bug_parts.append(bug)
        found = _differs(src, bug, name, gen, rng)
        assert found, (name, frm)
        args, (kind, value) = found
        if level == 3 and i == k - 1:
            continue  # the visible tests do not catch the last bug
        if kind == "ok":
            tests.append(f"assert {name}(*{args!r}) == {value!r}")
        else:
            tests.append(f"expect_value_error({name}, *{args!r})")
    ref = "\n\n".join(ref_parts)
    module = '"""Utility helpers. Each docstring is the specification."""\n\n\n' + "\n\n".join(bug_parts)
    test_file = (
        "from utils import *\n\n\ndef expect_value_error(fn, *args):\n    try:\n        fn(*args)\n"
        "    except ValueError:\n        return\n    raise AssertionError('expected ValueError')\n\n\n"
        + "\n".join(tests) + "\nprint('visible tests passed')\n"
    )
    gens = {n: TEMPLATES[n][2] for n in names}
    seed = rng.randint(0, 10**9)

    def check(answer, ref=ref, names=names, gens=gens, seed=seed):
        if isinstance(answer, dict) and len(answer) == 1:
            answer = next(iter(answer.values()))
        if not isinstance(answer, str) or not answer.strip():
            return 0.0
        harness = HARNESS.format(ref=ref, names=names, gens=gens, seed=seed)
        ok, out = run_python(harness, {"solution.py": answer})
        return 1.0 if "RESULT 1" in out else 0.0

    hidden = "Hidden tests check every function against its docstring." + (
        " The visible tests do not cover every bug." if level == 3 else ""
    )
    return Built(
        question=(
            f"utils.py has {k} bug{'s' if k > 1 else ''} (one per function at most). test_utils.py fails. Fix utils.py "
            f"so every function matches its docstring. {hidden} Submit the complete corrected contents of utils.py "
            "as the answer string."
        ),
        files={"utils.py": module, "test_utils.py": test_file},
        check=check,
        answer='"""Utility helpers. Each docstring is the specification."""\n\n\n' + ref,
        answer_hint="a string holding the whole fixed file, with newlines escaped as \\n inside the JSON string",
        budget={1: 8, 2: 10, 3: 12}[level],
        wrong=[module],
    )
