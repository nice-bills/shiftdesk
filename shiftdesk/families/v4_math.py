"""Math and formal reasoning v4: exact answers that need code, written to a file."""
import json
import math
from fractions import Fraction

from .base import Built
from .filetask import frac, graded, parse_json

DOMAIN = "mathematics-or-formal-reasoning"


def _solve(rows, ncols):
    """Gauss-Jordan over Fractions on an augmented matrix (rows of ncols+1).
    Returns (status, solution) with status in unique / none / many."""
    m = [[Fraction(x) for x in r] for r in rows]
    piv_cols = []
    r = 0
    for c in range(ncols):
        p = next((i for i in range(r, len(m)) if m[i][c] != 0), None)
        if p is None:
            continue
        m[r], m[p] = m[p], m[r]
        inv = 1 / m[r][c]
        m[r] = [x * inv for x in m[r]]
        for i in range(len(m)):
            if i != r and m[i][c] != 0:
                f = m[i][c]
                m[i] = [a - f * b for a, b in zip(m[i], m[r])]
        piv_cols.append(c)
        r += 1
        if r == len(m):
            break
    for i in range(r, len(m)):
        if m[i][ncols] != 0:
            return "none", None
    if len(piv_cols) < ncols:
        return "many", None
    sol = [Fraction(0)] * ncols
    for i, c in enumerate(piv_cols):
        sol[c] = m[i][ncols]
    return "unique", sol


def _fs(x):
    x = Fraction(x)
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


# --------------------------------------------------------------------------- expected turns
class BoardGame:
    NAME = "board-expectation"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        while True:
            out = BoardGame._try(level, rng)
            if out:
                return out

    @staticmethod
    def _try(level, rng):
        n = rng.randint(10, 18) if level == 1 else rng.randint(9, 14)
        d = rng.randint(3, 6) if level == 1 else rng.randint(3, 4)
        jumps = {}
        used = set()
        n_l = rng.randint(1, 3)
        n_s = 0 if level == 1 else rng.randint(1, 3)
        for kind, cnt in (("ladder", n_l), ("snake", n_s)):
            for _ in range(cnt):
                for _ in range(50):
                    a = rng.randint(1, n - 3) if kind == "ladder" else rng.randint(2, n - 1)
                    b = rng.randint(a + 1, n - 1) if kind == "ladder" else rng.randint(0, a - 1)
                    if a in used or b in used or a == b or b in jumps or (kind == "ladder" and b - a < 2):
                        continue
                    jumps[a] = b
                    used |= {a, b}
                    break
        exact = level == 2
        bonus = level == 2

        def move(s, f):
            t = s + f
            if t >= n:
                if exact and t > n:
                    return s, False
                return n, True
            t = jumps.get(t, t)
            return t, False

        states = [s for s in range(n) if s not in jumps]
        idx = {s: i for i, s in enumerate(states)}
        k = len(states)
        rows = []
        p = Fraction(1, d)
        if not bonus:
            for s in states:  # T(s) = 1 + sum p T(s')
                row = [Fraction(0)] * (k + 1)
                row[idx[s]] += 1
                row[k] = Fraction(1)
                for f in range(1, d + 1):
                    t, end = move(s, f)
                    if not end:
                        row[idx[t]] -= p
                rows.append(row)
            st, sol = _solve(rows, k)
            if st != "unique":
                return None
            val = sol[idx[0]]
        else:
            # T(s) = 1 + R(s); R(s) = sum_f p * (0 if end, R(s') if f == d else T(s'))
            for s in states:
                row = [Fraction(0)] * (2 * k + 1)
                row[idx[s]] = Fraction(1)
                row[k + idx[s]] = Fraction(-1)
                row[2 * k] = Fraction(1)
                rows.append(row)
            for s in states:
                row = [Fraction(0)] * (2 * k + 1)
                row[k + idx[s]] += 1
                for f in range(1, d + 1):
                    t, end = move(s, f)
                    if end:
                        continue
                    if f == d:
                        row[k + idx[t]] -= p
                    else:
                        row[idx[t]] -= p
                rows.append(row)
            st, sol = _solve(rows, 2 * k)
            if st != "unique":
                return None
            val = sol[idx[0]]
        if val.denominator == 1 or val > 200:
            return None
        lines = [f"Board: squares 0 to {n}. Every player starts on square 0; square {n} is home.",
                 f"Each roll: a fair die with faces 1 to {d}; move forward that many squares."]
        for a in sorted(jumps):
            b = jumps[a]
            lines.append(f"{'ladder' if b > a else 'snake'}: landing on {a} moves you to {b}")
        if exact:
            lines.append(f"You must land on {n} exactly; a roll that would pass {n} leaves you where you are (the turn still counts).")
        else:
            lines.append(f"Reaching or passing {n} ends the game.")
        if bonus:
            lines.append(f"Rolling a {d} gives one more roll in the same turn (this repeats for every {d} rolled), "
                         "unless that roll ended the game.")
        lines.append("Snakes and ladders act at the end of a move, before any bonus roll.")
        files = {"rules.txt": "\n".join(lines) + "\n"}
        q = ("A solo player plays the game in rules.txt. What is the exact expected number of turns until they reach "
             'home? Write output/answer.json as {"expected_turns": "p/q"} with a reduced fraction.')
        answer = json.dumps({"expected_turns": _fs(val)})

        def check(text, val=val):
            got = parse_json(text)
            return isinstance(got, dict) and frac(str(got.get("expected_turns", ""))) == val

        wrong = [json.dumps({"expected_turns": _fs(val + 1)}), json.dumps({"expected_turns": float(val)})]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/answer.json", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/answer.json")


# --------------------------------------------------------------------------- claim checking
def _sieve(n):
    s = bytearray([1]) * (n + 1)
    s[0:2] = b"\x00\x00"
    for i in range(2, int(n ** 0.5) + 1):
        if s[i]:
            s[i * i::i] = bytearray(len(s[i * i::i]))
    return s


def _isprime(x):
    if x < 2:
        return False
    if x % 2 == 0:
        return x == 2
    i = 3
    while i * i <= x:
        if x % i == 0:
            return False
        i += 2
    return True


def _lpf(x):
    best, f = 1, 2
    while f * f <= x:
        while x % f == 0:
            best, x = f, x // f
        f += 1
    return max(best, x)


def _sigma(n):
    s, i = 0, 1
    while i * i <= n:
        if n % i == 0:
            s += i + (n // i if i * i != n else 0)
        i += 1
    return s


def _collatz(n):
    c = 0
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        c += 1
    return c


def _three_sq(n):
    r = int(math.isqrt(n))
    for a in range(r + 1):
        for b in range(a, r + 1):
            c2 = n - a * a - b * b
            if c2 < b * b:
                break
            c = math.isqrt(c2)
            if c * c == c2:
                return True
    return False


def _claims(level):
    """Templates: (key, make(rng) -> (text, lo, hi, predicate over n, domain filter))."""
    P = _sieve(5000)

    def poly(rng):
        p = rng.choice([11, 17, 41])
        return f"n^2 + n + {p} is prime", 0, (lambda n, p=p: _isprime(n * n + n + p)), (lambda n: True), (p - 8, p + 25)

    def euler2(rng):
        return "n^2 - 79n + 1601 is prime", 0, (lambda n: _isprime(n * n - 79 * n + 1601)), (lambda n: True), (60, 110)

    def divides(rng):
        k, m = rng.choice([(5, 30), (7, 42), (3, 6), (4, 12), (5, 60), (6, 21), (9, 30), (13, 2730), (7, 84)])
        return f"{m} divides n^{k} - n", 1, (lambda n, k=k, m=m: (n ** k - n) % m == 0), (lambda n: True), (5, 40)

    def threesq(rng):
        return "n is a sum of three squares of non-negative integers", 1, _three_sq, (lambda n: True), (4, 30)

    def factsq(rng):
        return "n! + 1 is not a perfect square", 1, (lambda n: math.isqrt(math.factorial(n) + 1) ** 2 != math.factorial(n) + 1), (lambda n: True), (2, 9)

    def phieven(rng):
        return "Euler's totient phi(n) is even", 3, (lambda n: sum(1 for i in range(1, n + 1) if math.gcd(i, n) == 1) % 2 == 0), (lambda n: True), (20, 200)

    def goldbach(rng):
        return "the even number n is a sum of two primes", 4, (lambda n: any(P[i] and P[n - i] for i in range(2, n // 2 + 1))), (lambda n: n % 2 == 0), (100, 2000)

    def pseudo(rng):
        b = rng.choice([2, 3, 5])
        return (f"if {b}^(n-1) = 1 (mod n) then n is prime", 3, (lambda n, b=b: pow(b, n - 1, n) != 1 or P[n]),
                (lambda n: n % 2 == 1), {2: (300, 400), 3: (60, 130), 5: (150, 260)}[b])

    def lpf(rng):
        return "n^2 + 1 has a prime factor greater than n", 2, (lambda n: _lpf(n * n + 1) > n), (lambda n: True), (4, 30)

    def sigma3(rng):
        return "sigma(n), the sum of all positive divisors of n, is less than 3n", 1, (lambda n: _sigma(n) < 3 * n), (lambda n: True), (80, 200)

    def collatz(rng):
        s = rng.choice([20, 50, 100, 110])
        return (f"the Collatz map (n -> n/2 if n is even, else 3n+1) takes n to 1 within {s} steps", 1,
                (lambda n, s=s: _collatz(n) <= s), (lambda n: True), {20: (10, 60), 50: (20, 80), 100: (80, 150), 110: (100, 160)}[s])

    def digsum(rng):
        kk = rng.choice([5, 7, 13, 25, 29])
        return (f"the decimal digit sum of 2^n is not {kk}", 1, (lambda n, kk=kk: sum(map(int, str(2 ** n))) != kk),
                (lambda n: True), (5, 120))

    def mod4sq(rng):
        return ("the prime n is a sum of two squares", 5,
                (lambda n: any(math.isqrt(n - a * a) ** 2 == n - a * a for a in range(math.isqrt(n) + 1))),
                (lambda n: P[n] and n % 4 == 1), (50, 1000))

    easy = [poly, divides, threesq, factsq, phieven, goldbach]
    hard = [euler2, pseudo, lpf, sigma3, collatz, digsum, mod4sq, divides, poly]
    return easy if level == 1 else hard


class ClaimCheck:
    NAME = "claim-check"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        temps = _claims(level)
        k = 4 if level == 1 else 6
        picks = rng.sample(temps, k)
        claims, truth = [], {}
        for i, mk in enumerate(picks):
            text, lo, pred, dom, (a, b) = mk(rng)
            hi = rng.randint(a, b)
            cx = next((n for n in range(lo, hi + 1) if dom(n) and not pred(n)), None)
            cid = f"C{i + 1}"
            if dom(1) and dom(2):
                rng_txt = f"for every integer n with {lo} <= n <= {hi}"
            elif "even" in text:
                rng_txt = f"for every even n with {lo} <= n <= {hi}"
            elif "prime n" in text:
                rng_txt = f"for every prime n with n = 1 (mod 4) and {lo} <= n <= {hi}"
            else:
                rng_txt = f"for every odd n with {lo} <= n <= {hi}"
            claims.append(f"{cid}: {rng_txt}, {text}.")
            truth[cid] = cx
        files = {"claims.txt": "\n".join(claims) + "\n"}
        q = ("Check each claim in claims.txt exactly (by exhaustive computation over its stated range). Write "
             'output/verdicts.json mapping each claim id to {"holds": true} or {"holds": false, "counterexample": n}, '
             "where n is the SMALLEST n in the claim's range for which it fails.")
        ans = {c: ({"holds": True} if v is None else {"holds": False, "counterexample": v}) for c, v in truth.items()}
        answer = json.dumps(ans)

        def check(text, truth=truth):
            got = parse_json(text)
            if not isinstance(got, dict) or set(map(str, got)) != set(truth):
                return False
            for c, v in truth.items():
                g = got[c]
                if not isinstance(g, dict) or not isinstance(g.get("holds"), bool):
                    return False
                if v is None:
                    if g["holds"] is not True:
                        return False
                else:
                    ce = g.get("counterexample")
                    if g["holds"] is not False or isinstance(ce, bool) or ce not in (v, str(v)):
                        return False
            return True

        flip = dict(ans)
        c0 = next(iter(flip))
        flip[c0] = {"holds": True} if truth[c0] is not None else {"holds": False, "counterexample": 1}
        wrong = [json.dumps(flip), json.dumps({c: {"holds": True} for c in truth})]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/verdicts.json", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/verdicts.json")


# --------------------------------------------------------------------------- linear systems
def _term(c, v, first):
    if c == 0:
        return ""
    sign = "-" if c < 0 else ("" if first else "+")
    a = abs(c)
    body = (v if a == 1 else f"{a}{v}") if v else str(a)
    return f"{sign} {body}".strip() if not first else f"{sign}{body}"


def _side(terms):
    out = []
    for c, v in terms:
        t = _term(c, v, not out)
        if t:
            out.append(t)
    return " ".join(out) if out else "0"


class LinearSystem:
    NAME = "linear-system"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        n = rng.randint(3, 4) if level == 1 else rng.randint(5, 6)
        names = rng.choice([list("xyzwuv"), list("abcdef"), ["p", "q", "r", "s", "t", "u"], ["x1", "x2", "x3", "x4", "x5", "x6"]])[:n]
        while True:
            A = [[rng.randint(-6, 6) for _ in range(n)] for _ in range(n)]
            b = [rng.randint(-30, 30) for _ in range(n)]
            st, sol = _solve([r + [bb] for r, bb in zip(A, b)], n)
            if st == "unique" and any(x.denominator != 1 for x in sol) and all(any(r) for r in A):
                break
        eqs = [(r, bb) for r, bb in zip(A, b)]
        notes = ""
        if level == 2:
            i, j = rng.sample(range(n), 2)
            red = ([x + y for x, y in zip(A[i], A[j])], b[i] + b[j])
            bad = (list(A[rng.randrange(n)]), rng.randint(-30, 30))
            if sum(x * s for x, s in zip(bad[0], sol)) == bad[1]:
                bad = (bad[0], bad[1] + 1)
            eqs.append(red)
            pos = rng.randrange(len(eqs) + 1)
            eqs.insert(pos, bad)
            notes = (f"Lab notebook, page 2: equation E{pos + 1} was copied from the wrong run and must be ignored. "
                     "All other equations hold.\n")
        lines = []
        for k, (row, rhs) in enumerate(eqs):
            if level == 1:
                lines.append(f"E{k + 1}: {_side(list(zip(row, names)))} = {rhs}")
            else:
                terms = [(c, v) for c, v in zip(row, names) if c] + [(-rhs, "")]
                rng.shuffle(terms)
                left, right = [], []
                for c, v in terms:
                    (left if rng.random() < 0.5 else right).append((c, v))
                # sum(left) + sum(right) = 0, so show left = -(right)
                right = [(-c, v) for c, v in right]
                if rng.random() < 0.5:
                    k2 = rng.randint(-9, 9)
                    left.append((k2, ""))
                    right.append((k2, ""))
                lines.append(f"E{k + 1}: {_side(left)} = {_side(right)}")
        files = {"equations.txt": "\n".join(lines) + "\n"}
        if notes:
            files["notes.txt"] = notes
        q = (f"Solve the linear system in equations.txt for {', '.join(names)}" +
             (" (read notes.txt first)" if level == 2 else "") +
             '. Write output/solution.json mapping each variable to its exact value as a string, e.g. {"' +
             names[0] + '": "-7/3"}.')
        truth = dict(zip(names, sol))
        answer = json.dumps({k: _fs(v) for k, v in truth.items()})

        def check(text, truth=truth):
            got = parse_json(text)
            if not isinstance(got, dict) or set(got) != set(truth):
                return False
            return all(frac(got[k] if isinstance(got[k], (int, str)) else "x") == v for k, v in truth.items())

        wrong = [json.dumps({k: float(v) for k, v in truth.items()}),
                 json.dumps({k: _fs(v + (1 if i == 0 else 0)) for i, (k, v) in enumerate(truth.items())})]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/solution.json", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/solution.json")


# --------------------------------------------------------------------------- recurrences
MOD = 1_000_000_007


def _fit(terms, order, affine):
    rows = []
    for i in range(order, len(terms)):
        rows.append([terms[i - j] for j in range(1, order + 1)] + ([1] if affine else []) + [terms[i]])
    return _solve(rows, order + (1 if affine else 0))


def _matpow_term(coefs, d, init, m):
    """a_m mod MOD for a_n = sum c_j a_{n-j} + d, given a_0..a_{k-1}."""
    k = len(coefs)
    if m < k:
        return init[m] % MOD
    size = k + 1
    M = [[0] * size for _ in range(size)]
    M[0][:k] = [c % MOD for c in coefs]
    M[0][k] = d % MOD
    for i in range(1, k):
        M[i][i - 1] = 1
    M[k][k] = 1

    def mul(X, Y):
        return [[sum(X[i][t] * Y[t][j] for t in range(size)) % MOD for j in range(size)] for i in range(size)]

    R = [[int(i == j) for j in range(size)] for i in range(size)]
    e = m - (k - 1)
    while e:
        if e & 1:
            R = mul(R, M)
        M = mul(M, M)
        e >>= 1
    vec = [init[k - 1 - i] % MOD for i in range(k)] + [1]
    return sum(R[0][j] * vec[j] for j in range(size)) % MOD


class Recurrence:
    NAME = "recurrence-id"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        affine = level == 2
        show = 12 if level == 1 else 14
        while True:
            k = rng.choice([2, 3])
            coefs = [rng.randint(-3, 3) for _ in range(k)]
            if coefs[-1] == 0:
                continue
            d = rng.choice([x for x in range(-7, 8) if x]) if affine else 0
            init = [rng.randint(-5, 9) for _ in range(k)]
            terms = list(init)
            while len(terms) < show + 5:
                terms.append(sum(c * terms[-1 - j] for j, c in enumerate(coefs)) + d)
            if max(abs(t) for t in terms[:show]) > 10 ** 12 or len(set(terms[:show])) < show // 2:
                continue
            seen = terms[:show]
            # the intended form must be the unique smallest fit
            st, sol = _fit(seen, k, affine)
            if st != "unique" or [int(x) for x in sol[:k]] != coefs:
                continue
            smaller = any(_fit(seen, r, a)[0] != "none" for r in range(0, k + 1) for a in (False, True)
                          if (r, a) < (k, affine) and r + a >= 1 and (r < k or (r == k and not a)))
            if smaller:
                continue
            break
        files = {"sequence.txt": "Terms a_0, a_1, ... in order:\n" + ", ".join(map(str, seen)) + "\n"}
        if level == 1:
            q = ("sequence.txt holds the first terms of an integer sequence that satisfies a linear recurrence "
                 "a_n = c_1 a_{n-1} + ... + c_k a_{n-k} with constant integer coefficients. Find the one with the smallest "
                 'order k and write output/answer.json as {"coefficients": [c_1, ..., c_k], "next": [the next 5 terms]}.')
            truth = {"coefficients": coefs, "next": terms[show:show + 5]}
            answer = json.dumps(truth)
        else:
            m = rng.randint(200_000, 900_000)
            val = _matpow_term(coefs, d, init, m)
            q = ("sequence.txt holds the first terms of an integer sequence that satisfies a recurrence "
                 "a_n = c_1 a_{n-1} + ... + c_k a_{n-k} + d with constant integer coefficients and a constant integer d. "
                 "Find the form with the smallest k (d may be 0) and write output/answer.json as "
                 f'{{"coefficients": [c_1, ..., c_k], "constant": d, "term_mod": a_{m} mod 1000000007}} '
                 "(the term index starts at a_0; give the least non-negative residue).")
            truth = {"coefficients": coefs, "constant": d, "term_mod": val}
            answer = json.dumps(truth)

        def check(text, truth=truth):
            got = parse_json(text)
            if not isinstance(got, dict):
                return False
            for kk, v in truth.items():
                g = got.get(kk)
                if isinstance(v, list):
                    if not isinstance(g, list) or len(g) != len(v) or any(isinstance(x, bool) or x != y for x, y in zip(g, v)):
                        return False
                elif isinstance(g, bool) or g != v:
                    return False
            return True

        w1 = dict(truth)
        w1["coefficients"] = list(reversed(truth["coefficients"]))
        w2 = dict(truth)
        if level == 1:
            w2["next"] = truth["next"][1:] + [0]
        else:
            w2["term_mod"] = (truth["term_mod"] + 1) % MOD
        wrong = [json.dumps(w1), json.dumps(w2)]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/answer.json", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/answer.json")
