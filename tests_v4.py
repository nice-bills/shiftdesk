"""v4 gates. For every new file-deliverable family, an independent solver (written from the task text and the
visible files only, not from the generator) plays a full episode through the real tools and must earn reward 1;
the empty finish action, a wrong file, a missing file, the right content passed only as the submit answer, and
a symlinked deliverable all earn 0. Also checks the per-episode workdir persists across calls and is removed on
finish/reset/close, and that paths cannot escape it.

usage: python tests_v4.py [instances_per_task]
"""
import base64
import codecs
import csv
import hashlib
import hmac
import io
import itertools
import json
import math
import os
import random
import re
import struct
import sys
import wave
from datetime import datetime, timezone
from fractions import Fraction
from urllib.parse import unquote

sys.path.insert(0, '.')
from shiftdesk.families import parse_task_id, v4_task_ids
from shiftdesk.models import DeskAction
from shiftdesk.server.environment import DeskEnvironment

N = int(sys.argv[1]) if len(sys.argv) > 1 else 15


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def to_csv(header, rs):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rs)
    return buf.getvalue()


def ols(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs); sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    m = sxy / sxx
    return m, my - m * mx


# ------------------------------------------------------------------ science
def s_assay(q, f):
    unit = {"mg/l": 1.0, "ug/ml": 1.0, "ng/ul": 1.0, "g/l": 1000.0, "ug/l": 0.001}
    flagged = {r["well"] for r in rows(f["qc_flags.txt"])} if "qc_flags.txt" in f else set()
    data = [r for r in rows(f["plate.csv"]) if r["well"] not in flagged]
    b0 = sum(float(r["signal"]) for r in data if r["type"] == "blank") / sum(r["type"] == "blank" for r in data)
    st = [(float(r["conc"]) * unit[(r["unit"] or "mg/L").lower()], float(r["signal"]) - b0) for r in data if r["type"] == "std"]
    m, b = ols([x for x, _ in st], [y for _, y in st])
    top = max(st)[1]
    ids = sorted({r["id"] for r in data if r["type"] == "sample"} | {r["id"] for r in rows(f["plate.csv"]) if r["type"] == "sample"})
    lvl2 = "status" in q
    out = []
    for sid in ids:
        ws = [r for r in data if r["id"] == sid]
        y = sum(float(r["signal"]) for r in ws) / len(ws) - b0
        c = (y - b) / m * float(ws[0]["dilution"])
        if lvl2:
            out.append([sid, "", "above_range"] if y > top else [sid, f"{c:.6f}", "ok"])
        else:
            out.append([sid, f"{c:.6f}"])
    return to_csv(["sample_id", "conc_mg_per_L"] + (["status"] if lvl2 else []), out)


def s_peaks(q, f):
    lines = f["spectrum.csv"].strip().splitlines()
    key = "position_cm1" if lines[0].startswith("wavenumber") else "position_nm"
    xs = [float(l.split(",")[0]) for l in lines[1:]]; ys = [float(l.split(",")[1]) for l in lines[1:]]
    sop = f["sop.md"]
    if "Baseline" in sop:
        wins = [tuple(map(float, w)) for w in re.findall(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?) nm", sop)]
        sel = [(x, y) for x, y in zip(xs, ys) if any(a <= x <= b for a, b in wins)]
        m, b = ols([x for x, _ in sel], [y for _, y in sel])
        ys = [y - (m * x + b) for x, y in zip(xs, ys)]
        orig = list(ys)
        for i in range(1, len(ys) - 1):
            if orig[i] - orig[i - 1] > 60 and orig[i] - orig[i + 1] > 60:
                ys[i] = (orig[i - 1] + orig[i + 1]) / 2
    thr = float(re.search(r"at least ([\d.]+)", sop).group(1))
    win = float(re.search(r"within \+/-([\d.]+)", sop).group(1))
    out = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        if y >= thr and all(ys[j] < y for j in range(len(xs)) if j != i and abs(xs[j] - x) <= win):
            out.append({key: x, "height": round(y, 3)})
    return json.dumps(out)


def s_dilution(q, f):
    cu = {"m": 1e6, "mm": 1e3, "um": 1.0, "nm": 1e-3}
    rg = f["reagent.txt"]
    if "targets.csv" in f:
        stock = float(re.search(r"at ([\d.]+) mM", rg).group(1)) * 1e3
        out = []
        for r in rows(f["targets.csv"]):
            c = float(r["target_conc"]) * cu[r["unit"].lower()]
            v = float(r["final_volume_uL"])
            s = c / stock * v
            out.append([r["tube"], f"{s:.5f}", f"{v - s:.5f}"])
        return to_csv(["tube", "stock_uL", "diluent_uL"], out)
    mm = float(re.search(r"molar mass ([\d.]+)", rg).group(1))
    mgml = float(re.search(r"at ([\d.]+) mg/mL", rg).group(1))
    stock = mgml / mm * 1e6
    rs = rows(f["series.csv"])
    cs = [float(r["target_conc"]) * cu[r["unit"].lower()] for r in rs]
    out = [None] * len(rs)
    carry = 0.0
    for k in range(len(rs) - 1, -1, -1):
        tot = float(rs[k]["volume_needed_uL"]) + carry
        src = stock if k == 0 else cs[k - 1]
        t = tot * cs[k] / src
        out[k] = [rs[k]["tube"], "stock" if k == 0 else rs[k - 1]["tube"], f"{t:.5f}", f"{tot - t:.5f}"]
        carry = t
    return to_csv(["tube", "source", "transfer_uL", "diluent_uL"], out)


def s_pk(q, f):
    data = []
    if "dosing.txt" in f:
        dose = datetime.strptime(re.search(r"given (\d{4}-\d\d-\d\d \d\d:\d\d)", f["dosing.txt"]).group(1), "%Y-%m-%d %H:%M")
        for r in rows(f["plasma.csv"]):
            t = (datetime.strptime(r["collected_at"], "%Y-%m-%d %H:%M") - dose).total_seconds() / 3600
            if r["result"] == "BLQ":
                data.append((t, None))
            else:
                data.append((t, float(r["result"]) * (1000 if r["unit"] == "ug/mL" else 1)))
    else:
        data = [(float(r["time_h"]), float(r["conc_ng_mL"])) for r in rows(f["plasma.csv"])]
    data.sort()
    q_ = [(t, c) for t, c in data if c is not None]
    tmax, cmax = max(q_, key=lambda p: p[1])
    pts = [(0.0, 0.0)] + [(t, 0.0 if c is None else c) for t, c in data if c is not None or t < tmax]
    auc = sum((b[0] - a[0]) * (a[1] + b[1]) / 2 for a, b in zip(pts, pts[1:]))
    last4 = q_[-4:]
    m, _ = ols([t for t, _ in last4], [math.log(c) for _, c in last4])
    k = -m
    return json.dumps({"k_el_per_h": k, "half_life_h": math.log(2) / k, "auc_0_last": auc,
                       "auc_0_inf": auc + last4[-1][1] / k, "cmax": cmax, "tmax_h": tmax})


# ------------------------------------------------------------------ math
def parse_lin(expr):
    expr = expr.replace(" ", "")
    if not expr.startswith(("+", "-")):
        expr = "+" + expr
    co, const = {}, Fraction(0)
    for sign, num, var in re.findall(r"([+-])(\d*)([a-z]\d?)?", expr):
        if not num and not var:
            continue
        v = Fraction(int(num) if num else 1) * (-1 if sign == "-" else 1)
        if var:
            co[var] = co.get(var, 0) + v
        else:
            const += v
    return co, const


def s_linear(q, f):
    ignore = set(re.findall(r"equation (E\d+)", f.get("notes.txt", "")))
    names = [v.strip() for v in re.search(r"for (.*?)(?: \(read|\.)", q).group(1).split(",")]
    eqs = []
    for line in f["equations.txt"].splitlines():
        eid, body = line.split(":", 1)
        if eid in ignore:
            continue
        l, r = body.split("=")
        cl, kl = parse_lin(l); cr, kr = parse_lin(r)
        eqs.append([cl.get(n, 0) - cr.get(n, 0) for n in names] + [kr - kl])
    # least squares is not exact; do exact elimination on a square subset that is consistent with all
    import sympy
    M = sympy.Matrix([[sympy.Rational(x.numerator, x.denominator) if isinstance(x, Fraction) else x for x in e] for e in eqs])
    sol = sympy.linsolve((M[:, :-1], M[:, -1]))
    (vals,) = list(sol)
    return json.dumps({n: str(sympy.Rational(v)) for n, v in zip(names, vals)})


def s_recur(q, f):
    terms = [int(x) for x in f["sequence.txt"].splitlines()[1].split(",")]
    affine_ok = "+ d" in q
    import sympy
    for k in range(1, 6):
        for aff in ((False, True) if affine_ok else (False,)):
            A = sympy.Matrix([[terms[i - j] for j in range(1, k + 1)] + ([1] if aff else []) for i in range(k, len(terms))])
            bvec = sympy.Matrix(terms[k:])
            sols = list(sympy.linsolve((A, bvec)))
            if not sols:
                continue
            s = sols[0]
            if any(x.free_symbols for x in s):
                continue
            co = [int(x) for x in s[:k]]
            d = int(s[k]) if aff else 0
            if not affine_ok:
                seq = list(terms)
                for _ in range(5):
                    seq.append(sum(c * seq[-1 - j] for j, c in enumerate(co)))
                return json.dumps({"coefficients": co, "next": seq[len(terms):]})
            m = int(re.search(r"a_(\d+) mod", q).group(1))
            P = 1_000_000_007
            # matrix power with numpy-free pure python
            size = k + 1
            M = [[0] * size for _ in range(size)]
            M[0][:k] = [c % P for c in co]; M[0][k] = d % P
            for i in range(1, k):
                M[i][i - 1] = 1
            M[k][k] = 1

            def mul(X, Y):
                return [[sum(X[i][t] * Y[t][j] for t in range(size)) % P for j in range(size)] for i in range(size)]
            R = [[int(i == j) for j in range(size)] for i in range(size)]
            e = m - (k - 1)
            while e > 0:
                if e & 1:
                    R = mul(R, M)
                M = mul(M, M); e >>= 1
            vec = [terms[k - 1 - i] % P for i in range(k)] + [1]
            return json.dumps({"coefficients": co, "constant": d, "term_mod": sum(R[0][j] * vec[j] for j in range(size)) % P})
    raise ValueError("no recurrence")


def isprime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True


def s_claims(q, f):
    out = {}
    for line in f["claims.txt"].splitlines():
        cid, rest = line.split(": ", 1)
        rng_part, claim = rest.split(", ", 1)
        claim = claim.rstrip(".")
        lo, hi = map(int, re.search(r"(\d+) <= n <= (\d+)", rng_part).groups())
        ns = range(lo, hi + 1)
        if "even n" in rng_part:
            ns = [n for n in ns if n % 2 == 0]
        elif "odd n" in rng_part:
            ns = [n for n in ns if n % 2 == 1]
        elif "prime n" in rng_part:
            ns = [n for n in ns if isprime(n) and n % 4 == 1]
        m = re.fullmatch(r"n\^2 \+ n \+ (\d+) is prime", claim)
        if m:
            p = int(m.group(1)); pred = lambda n: isprime(n * n + n + p)
        elif claim == "n^2 - 79n + 1601 is prime":
            pred = lambda n: isprime(n * n - 79 * n + 1601)
        elif re.fullmatch(r"\d+ divides n\^\d+ - n", claim):
            mm, kk = map(int, re.fullmatch(r"(\d+) divides n\^(\d+) - n", claim).groups())
            pred = lambda n: (n ** kk - n) % mm == 0
        elif claim.startswith("n is a sum of three squares"):
            pred = lambda n: any(a * a + b * b + c * c == n for a in range(12) for b in range(12) for c in range(12))
        elif claim.startswith("n! + 1"):
            pred = lambda n: math.isqrt(math.factorial(n) + 1) ** 2 != math.factorial(n) + 1
        elif claim.startswith("Euler's totient"):
            pred = lambda n: sum(math.gcd(i, n) == 1 for i in range(1, n + 1)) % 2 == 0
        elif claim.startswith("the even number"):
            pred = lambda n: any(isprime(i) and isprime(n - i) for i in range(2, n // 2 + 1))
        elif claim.startswith("if "):
            b = int(re.match(r"if (\d+)\^", claim).group(1)); pred = lambda n: pow(b, n - 1, n) != 1 or isprime(n)
        elif claim.startswith("n^2 + 1 has a prime factor"):
            def pred(n):
                x = n * n + 1
                return max(p for p in range(2, x + 1) if x % p == 0 and isprime(p)) > n
        elif claim.startswith("sigma(n)"):
            pred = lambda n: sum(d for d in range(1, n + 1) if n % d == 0) < 3 * n
        elif claim.startswith("the Collatz"):
            s = int(re.search(r"within (\d+) steps", claim).group(1))
            def pred(n, s=s):
                c = 0
                while n != 1:
                    n = n // 2 if n % 2 == 0 else 3 * n + 1; c += 1
                return c <= s
        elif claim.startswith("the decimal digit sum"):
            kk = int(re.search(r"is not (\d+)", claim).group(1)); pred = lambda n: sum(map(int, str(2 ** n))) != kk
        elif claim.startswith("the prime n is a sum of two squares"):
            pred = lambda n: any(math.isqrt(n - a * a) ** 2 == n - a * a for a in range(math.isqrt(n) + 1))
        else:
            raise ValueError(claim)
        cx = next((n for n in ns if not pred(n)), None)
        out[cid] = {"holds": True} if cx is None else {"holds": False, "counterexample": cx}
    return json.dumps(out)


def s_board(q, f):
    r = f["rules.txt"]
    n = int(re.search(r"squares 0 to (\d+)", r).group(1))
    d = int(re.search(r"faces 1 to (\d+)", r).group(1))
    jumps = {int(a): int(b) for a, b in re.findall(r"landing on (\d+) moves you to (\d+)", r)}
    exact = "exactly" in r
    bonus = "one more roll" in r
    import sympy
    T = {s: sympy.Symbol(f"T{s}") for s in range(n)}
    R = {s: sympy.Symbol(f"R{s}") for s in range(n)}

    def mv(s, fc):
        t = s + fc
        if t >= n:
            return (None if (not exact or t == n) else s)
        return jumps.get(t, t)
    eqs = []
    for s in range(n):
        if s in jumps:
            continue
        if not bonus:
            eqs.append(sympy.Eq(T[s], 1 + sum(sympy.Rational(1, d) * T[mv(s, fc)] for fc in range(1, d + 1) if mv(s, fc) is not None)))
        else:
            eqs.append(sympy.Eq(T[s], 1 + R[s]))
            eqs.append(sympy.Eq(R[s], sum(sympy.Rational(1, d) * (R[mv(s, fc)] if fc == d else T[mv(s, fc)])
                                          for fc in range(1, d + 1) if mv(s, fc) is not None)))
    syms = [T[s] for s in range(n) if s not in jumps] + ([R[s] for s in range(n) if s not in jumps] if bonus else [])
    sol = sympy.solve(eqs, syms, dict=True)[0]
    return json.dumps({"expected_turns": str(sympy.Rational(sol[T[0]]))})


# ------------------------------------------------------------------ security
LOG = re.compile(r'(\S+) - - \[([^\]]+)\] "(\S+) (\S+) [^"]*" (\d+) (\d+)')


def s_web(q, f):
    ev = []
    for l in f["access.log"].splitlines():
        m = LOG.match(l)
        ip, ts, meth, path, st, sz = m.groups()
        ev.append((datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z"), ip, path, int(st)))
    if "SQL injection" in q:
        pat = re.compile(r"union(\s|%20)+(all(\s|%20)+)?select|'\s*or\s*'?1'?\s*=\s*'?1|%27(\s|%20)*or|sleep\(|;drop|'--|--$", re.I)
        sus = {e[1] for e in ev if pat.search(unquote(e[2])) or pat.search(e[2])}
        assert len(sus) == 1, sus
        ip = sus.pop()
        mine = [e for e in ev if e[1] == ip]
        p200 = sorted({e[2] for e in mine if e[3] == 200 and (pat.search(unquote(e[2])) or pat.search(e[2]))})
    else:
        cnt = {}
        for e in ev:
            if e[3] == 404:
                cnt.setdefault(e[1], set()).add(e[2])
        ip = max(cnt, key=lambda k: len(cnt[k]))
        mine = [e for e in ev if e[1] == ip]
        p200 = sorted({e[2] for e in mine if e[3] == 200})
    ts = sorted(e[0] for e in mine)
    z = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return json.dumps({"attacker_ip": ip, "first_seen": z(ts[0]), "last_seen": z(ts[-1]), "request_count": len(mine), "paths_200": p200})


def s_decode(q, f):
    key = bytes.fromhex(re.search(r"\(hex\): ([0-9a-f]+)", f["notes.txt"]).group(1))
    ok = re.compile(r"flag\{[a-z0-9-]+\}")

    def peel(data, depth):
        if ok.fullmatch(data):
            return data
        if depth == 0:
            return None
        cands = []
        try:
            cands.append(base64.b64decode(data, validate=True).decode("latin-1"))
        except Exception:
            pass
        try:
            raw = bytes.fromhex(data)
            cands.append(raw.decode("latin-1"))
            cands.append(bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("latin-1"))
        except Exception:
            pass
        cands.append(codecs.decode(data, "rot13"))
        if "%" in data:
            cands.append(unquote(data, encoding="latin-1"))
        for c in cands:
            if c != data:
                r = peel(c, depth - 1)
                if r:
                    return r
        return None
    blobs, hashes = {}, {}
    words = f["wordlist.txt"].split()
    for line in f["artefacts.txt"].splitlines():
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if parts[0].startswith("B"):
            blobs[parts[0]] = peel(parts[1], 4)
        else:
            h, salt = parts[1], ("" if parts[2] == "-" else parts[2])
            alg = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}[len(h)]
            pw = next(w for w in words if hashlib.new(alg, (salt + w).encode()).hexdigest() == h)
            hashes[parts[0]] = {"algorithm": alg, "password": pw}
    return json.dumps({"blobs": blobs, "hashes": hashes})


def s_sshd(q, f):
    base = f["baseline.md"]
    defaults = {}
    m = re.search(r"OpenSSH defaults: (.*)\.", base)
    stock = {"permitrootlogin": "prohibit-password", "passwordauthentication": "yes", "permitemptypasswords": "no",
             "maxauthtries": "6", "x11forwarding": "no", "logingracetime": "120", "ciphers": "aes128-ctr",
             "allowtcpforwarding": "yes", "clientaliveinterval": "0", "usepam": "no", "loglevel": "info",
             "hostbasedauthentication": "no"}
    defaults.update(stock)
    if m:
        for part in m.group(1).split("; "):
            k, v = part.split(" ", 1)
            defaults[k.lower()] = v.lower()
    eff = {}
    for line in f["sshd_config"].splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("match "):
            break
        mm = re.match(r"(\S+?)(?:\s*=\s*|\s+)(.*)", s)
        k, v = mm.group(1).lower(), mm.group(2).strip().lower()
        eff.setdefault(k, v)

    def secs(v):
        tot = 0
        for n, u in re.findall(r"(\d+)([smhdw]?)", v):
            tot += int(n) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[u]
        return tot
    tests = {
        "SSH-01": lambda v: v == "no", "SSH-02": lambda v: v == "no", "SSH-03": lambda v: v == "no",
        "SSH-04": lambda v: int(v) <= 4, "SSH-05": lambda v: v == "no", "SSH-06": lambda v: 0 < secs(v) <= 60,
        "SSH-07": lambda v: not re.search(r"cbc|arcfour|3des", v), "SSH-08": lambda v: v == "no",
        "SSH-09": lambda v: 0 < int(v) <= 300, "SSH-10": lambda v: v == "yes", "SSH-11": lambda v: v in ("info", "verbose"),
        "SSH-12": lambda v: v == "no"}
    kws = {"SSH-01": "permitrootlogin", "SSH-02": "passwordauthentication", "SSH-03": "permitemptypasswords",
           "SSH-04": "maxauthtries", "SSH-05": "x11forwarding", "SSH-06": "logingracetime", "SSH-07": "ciphers",
           "SSH-08": "allowtcpforwarding", "SSH-09": "clientaliveinterval", "SSH-10": "usepam", "SSH-11": "loglevel",
           "SSH-12": "hostbasedauthentication"}
    failing = []
    for rid in re.findall(r"^(SSH-\d\d):", base, re.M):
        kw = kws[rid]
        if not tests[rid](eff.get(kw, defaults[kw])):
            failing.append(rid)
    return json.dumps({"failing": sorted(failing)})


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def s_jwt(q, f):
    v = f["verifier.md"]
    now = int(re.search(r"now \(unix seconds, UTC\): (\d+)", v).group(1))
    iss = re.search(r"expected issuer: (\S+)", v).group(1)
    aud = re.search(r"expected audience: (\S+)", v)
    keys = dict(re.findall(r"key (k\d+): (\S+)", v))
    single = re.search(r"secret \(UTF-8 bytes\): (\S+)", v)
    order = [x.strip() for x in re.search(r"in this order: (.*)\.", v).group(1).split(",")]
    out = {}
    for line in f["tokens.txt"].splitlines():
        tid, tok = line.split()
        h, p, sig = tok.split(".")
        H, P = json.loads(b64d(h)), json.loads(b64d(p))
        key = single.group(1) if single else keys.get(H.get("kid"))
        checks = {
            "alg_none": lambda: H.get("alg", "").lower() == "none",
            "unknown_kid": lambda: key is None,
            "bad_signature": lambda: not hmac.compare_digest(b64d(sig), hmac.new(key.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()),
            "expired": lambda: now >= P["exp"],
            "not_yet_valid": lambda: "nbf" in P and now < P["nbf"],
            "wrong_issuer": lambda: P.get("iss") != iss,
            "wrong_audience": lambda: aud.group(1) not in (P.get("aud") if isinstance(P.get("aud"), list) else [P.get("aud")]),
        }
        reason = next((r for r in order if checks[r]()), "ok")
        out[tid] = {"valid": reason == "ok", "reason": reason, "sub": P.get("sub")}
    return json.dumps(out)


# ------------------------------------------------------------------ media
def ms(s):
    h, m, rest = s.strip().split(":")
    sec, milli = rest.split(",")
    return ((int(h) * 60 + int(m)) * 60 + int(sec)) * 1000 + int(milli)


def fmt(t):
    return f"{t // 3600000:02d}:{t // 60000 % 60:02d}:{t // 1000 % 60:02d},{t % 1000:03d}"


def s_srt(q, f):
    cues = []
    for b in f["subs.srt"].strip().split("\n\n"):
        ls = b.split("\n")
        a, c = ls[1].split(" --> ")
        cues.append((ms(a), ms(c), "\n".join(ls[2:])))
    if "sync.txt" in f:
        pts = re.findall(r"cue (\d+) .*START at (\S+)", f["sync.txt"])
        (i1, t1), (i2, t2) = [(int(i) - 1, ms(t)) for i, t in pts]
        k = (t2 - t1) / (cues[i2][0] - cues[i1][0])
        lin = lambda x: int(math.floor(t1 + (x - cues[i1][0]) * k + 0.5))
        out = []
        for s, e, x in cues:
            if x.startswith("[") and x.endswith("]"):
                continue
            if lin(e) <= 0:
                continue
            out.append((max(0, lin(s)), lin(e), x))
    else:
        off = int(re.search(r"(\d+) ms", q).group(1)) * (-1 if "earlier" in q else 1)
        out = [(s + off, e + off, x) for s, e, x in cues]
    return "\n".join(f"{i}\n{fmt(s)} --> {fmt(e)}\n{x}\n" for i, (s, e, x) in enumerate(out, 1))


def s_images(q, f):
    from PIL import Image
    spec = f["spec.md"]
    mw, mh = map(int, re.search(r"within (\d+) x (\d+)", spec).groups())
    allowed = [x.strip() for x in re.search(r"Allowed formats: (.*)\.", spec).group(1).split(",")]
    lvl2 = "EXIF" in spec
    out = []
    for name in sorted(k for k in f if k.startswith("assets/")):
        im = Image.open(io.BytesIO(f[name]))
        fm = im.format
        w, h = im.size
        if lvl2 and im.getexif().get(0x0112, 1) in (5, 6, 7, 8):
            w, h = h, w
        rs = []
        if fm not in allowed:
            rs.append("format")
        if w > mw or h > mh:
            rs.append("size")
        if lvl2:
            ext = name.rsplit(".", 1)[1].lower()
            if {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "GIF", "webp": "WEBP"}[ext] != fm:
                rs.append("extension")
        out.append([name, fm, w, h, "true" if not rs else "false", ";".join(rs)])
    return to_csv(["file", "format", "width", "height", "ok", "reasons"], out)


def s_audio(q, f):
    lvl2 = "clipping" in q
    out = []
    for name in sorted(k for k in f if k.endswith(".wav")):
        with wave.open(io.BytesIO(f[name])) as w:
            rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
            raw = w.readframes(n)
        vals = struct.unpack(f"<{len(raw) // 2}h", raw)
        peak = max(abs(v) for v in vals)
        row = [name, rate, ch, f"{n / rate:.3f}", f"{20 * math.log10(peak / 32768):.2f}"]
        if lvl2:
            clipped = sum(1 for v in vals if v >= 32767 or v <= -32767)
            row += [clipped, "true" if clipped >= 3 else "false"]
        out.append(row)
    return to_csv(["file", "sample_rate", "channels", "duration_s", "peak_dbfs"] + (["clipped_samples", "clipping"] if lvl2 else []), out)


def s_md(q, f):
    lvl2 = "<em>" in f["style.md"]
    seen_h1 = False
    slugs = {}

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def inline(s):
        s = esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        if lvl2:
            s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)

        def link(m):
            label, url = m.group(1), m.group(2)
            extra = ' target="_blank" rel="noopener noreferrer"' if lvl2 and re.match(r"https?://", url) else ""
            return f'<a href="{url}"{extra}>{label}</a>'
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, s)
    out, para, items = [], [], []

    def flush():
        nonlocal para, items
        if para:
            out.append("<p>" + " ".join(inline(x) for x in para) + "</p>")
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
        para, items = [], []
    for line in f["article.md"].splitlines():
        m = re.match(r"(#{1,6}) (.*)", line)
        if m:
            flush()
            lv = len(m.group(1)); text = m.group(2)
            if lvl2:
                if lv == 1:
                    if seen_h1:
                        lv = 2
                    seen_h1 = True
                sl = re.sub(r"[\s-]+", "-", re.sub(r"[^a-z0-9\s-]", "", text.lower())).strip("-")
                if sl in slugs:
                    slugs[sl] += 1; sl = f"{sl}-{slugs[sl]}"
                else:
                    slugs[sl] = 1
                out.append(f'<h{lv} id="{sl}">{esc(text)}</h{lv}>')
            else:
                out.append(f"<h{lv}>{esc(text)}</h{lv}>")
        elif not line.strip():
            flush()
        elif line.startswith("- "):
            if para:
                flush()
            items.append(line[2:])
        else:
            if items:
                flush()
            para.append(line)
    flush()
    return "\n".join(out) + "\n"


SOLVERS = {
    "assay-reduction": s_assay, "peak-picking": s_peaks, "dilution-plan": s_dilution, "pk-fit": s_pk,
    "linear-system": s_linear, "recurrence-id": s_recur, "claim-check": s_claims, "board-expectation": s_board,
    "web-forensics": s_web, "decode-chain": s_decode, "sshd-audit": s_sshd, "jwt-inspect": s_jwt,
    "srt-retime": s_srt, "image-audit": s_images, "audio-audit": s_audio, "markdown-html": s_md,
}


# ------------------------------------------------------------------ episodes
def act(env, tool, **args):
    return env.step(DeskAction(tool=tool, args=args))


def deliver(env, path, content, how):
    """Write the deliverable with one of the three writing tools."""
    if how == "write_file":
        o = act(env, "write_file", path=path, content=content)
    elif how == "bash":
        b64 = base64.b64encode(content.encode()).decode()
        o = act(env, "bash", command=f"mkdir -p $(dirname {path}) && echo '{b64}' | base64 -d > {path} && wc -c {path}")
    else:
        o = act(env, "run_python", code=f"import base64\nopen({path!r}, 'wb').write(base64.b64decode({base64.b64encode(content.encode()).decode()!r}))\nprint('ok')")
    assert o.ok and not o.done, (how, o.output)
    return o


def main():
    bad = 0
    hows = ["write_file", "bash", "run_python"]
    for i, tid in enumerate(v4_task_ids()):
        fam, lvl = parse_task_id(tid)
        solver = SOLVERS[fam.NAME]
        miss = 0
        for s in range(N):
            env = DeskEnvironment(allow_seed=True)
            o = env.reset(seed=f"v4-{s}", task_id=tid)
            b = env._ep["built"]
            assert b.deliverable and b.deliverable in o.output
            # the solver sees only the question and the task files
            try:
                content = solver(b.question, dict(b.files))
            except Exception as e:
                content = None
                err = f"{type(e).__name__}: {e}"
            if content is None:
                miss += 1
                print("  SOLVER ERROR", tid, s, err)
                env.close(); continue
            # read the files through the tools first, as a policy would
            o = act(env, "bash", command="ls -la; ls output")
            assert o.ok and "output" in o.output, o.output
            deliver(env, b.deliverable, content, hows[(i + s) % 3])
            o = act(env, "read_file", path=b.deliverable)  # files the policy wrote are readable
            assert o.ok and not o.done, o.output
            o = act(env, "submit", answer="")
            if not (o.done and o.reward == 1.0):
                miss += 1
                if miss <= 2:
                    print("  MISMATCH", tid, s, "\n  solver:", content[:400], "\n  ref:   ", b.answer[:400])
            # failure modes, all must be 0
            env.reset(seed=f"v4-{s}", task_id=tid)
            z1 = act(env, "submit", answer="").reward                                  # empty finish
            env.reset(seed=f"v4-{s}", task_id=tid)
            z2 = act(env, "submit", answer=content).reward                             # right content, no file
            env.reset(seed=f"v4-{s}", task_id=tid)
            act(env, "write_file", path=b.deliverable, content="")                      # empty file
            z3 = act(env, "submit", answer="").reward
            env.reset(seed=f"v4-{s}", task_id=tid)
            act(env, "write_file", path="decoy.txt", content=content)                   # symlinked deliverable
            act(env, "bash", command=f"rm -f {b.deliverable}; ln -s ../decoy.txt {b.deliverable}")
            z4 = act(env, "submit", answer="").reward
            z5 = 0.0
            if b.wrong:
                env.reset(seed=f"v4-{s}", task_id=tid)
                act(env, "write_file", path=b.deliverable, content=b.wrong[0])
                z5 = act(env, "submit", answer="").reward
            if any(z != 0.0 for z in (z1, z2, z3, z4, z5)):
                miss += 1
                print("  NONZERO FAILURE MODE", tid, s, (z1, z2, z3, z4, z5))
            env.close()
        bad += miss
        print(f"{tid:24s} independent solver earns 1 on {N - miss}/{N}; empty/no-file/symlink/wrong earn 0")

    # workdir lifecycle and path safety
    env = DeskEnvironment(allow_seed=True)
    env.reset(seed=1, task_id="linear-system-L1")
    root = env._wd.root
    assert act(env, "write_file", path="scratch/a.txt", content="hello").ok
    o = act(env, "bash", command="cat scratch/a.txt && echo more >> scratch/a.txt && pwd")
    assert "hello" in o.output and root not in o.output, o.output
    o = act(env, "run_python", code="print(open('scratch/a.txt').read().split())")
    assert "'hellomore'" in o.output, o.output
    o = act(env, "write_file", path="../escape.txt", content="x")
    assert not o.ok, o.output
    o = act(env, "write_file", path="/etc/escape.txt", content="x")
    assert not o.ok, o.output
    o = act(env, "read_file", path="../../etc/passwd")
    assert not o.ok, o.output
    o = act(env, "bash", command="sleep 60")
    assert "killed after" in o.output, o.output
    o = act(env, "list_files")
    assert "scratch/a.txt" in o.output and "equations.txt" in o.output, o.output
    env.reset(seed=1, task_id="linear-system-L1")
    assert not os.path.exists(root), "workdir not removed on reset"
    root = env._wd.root
    act(env, "submit", answer="")
    assert not os.path.exists(root), "workdir not removed on finish"
    # running out of calls grades the deliverable as it stands
    env.reset(seed=1, task_id="sshd-audit-L1")
    b = env._ep["built"]
    act(env, "write_file", path=b.deliverable, content=b.answer)
    for _ in range(b.budget - 1):
        o = act(env, "list_files")
    assert o.done and o.reward == 1.0, (o.done, o.reward)
    env.reset(seed=1, task_id="sshd-audit-L1")
    root = env._wd.root
    env.close()
    assert not os.path.exists(root), "workdir not removed on close"
    print("workdir lifecycle and path checks ok")
    print("V4 BAD", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
