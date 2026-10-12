"""Math and formal reasoning v3 families."""
import heapq
import itertools
import math
from fractions import Fraction

from ..grading import exact_int, fields, load, same_fraction, same_list, same_text
from .base import Built

DOMAIN = "mathematics-or-formal-reasoning"


# ---------------------------------------------------------------- CRT
class Congruences:
    NAME = "congruences"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        while True:
            k = 3 if level == 1 else 4
            if level == 1:
                mods = rng.sample([5, 7, 9, 11, 13, 16, 17, 19, 23], k)
                if any(math.gcd(a, b) > 1 for a, b in itertools.combinations(mods, 2)):
                    continue
            else:
                mods = rng.sample([6, 8, 9, 10, 12, 14, 15, 18, 20, 21, 25, 28], k)
            L = 1
            for m in mods:
                L = L * m // math.gcd(L, m)
            x = rng.randrange(L)
            res = [x % m for m in mods]
            if L < 500:
                continue
            lo = rng.randrange(10 ** 4, 10 ** 5)
            hi = lo + rng.randrange(3, 9) * L + rng.randrange(L)
            count = sum(1 for v in range(lo, hi + 1) if v % L == x)
            break
        lines = ["Find every integer x that satisfies all of these congruences:"]
        lines += [f"  x = {r} (mod {m})" for r, m in zip(res, mods)]
        prod = 1
        for m in mods:
            prod *= m
        if level == 2:
            lines.append(f"Also count the solutions x with {lo} <= x <= {hi}.")
        checks = {"x": lambda v: exact_int(v, x), "modulus": lambda v: exact_int(v, L)}
        ans = {"x": x, "modulus": L}
        hint = '{"x": 1234, "modulus": 5040}'
        if level == 2:
            checks["count_in_range"] = lambda v: exact_int(v, count)
            ans["count_in_range"] = count
            hint = '{"x": 1234, "modulus": 5040, "count_in_range": 7}'
        return Built(
            question=("system.txt lists a system of congruences. Give the smallest non-negative solution x and the "
                      "modulus M such that the solutions are exactly x + k*M" + (", and the count it asks for." if level == 2 else ".")),
            files={"system.txt": "\n".join(lines) + "\n"},
            check=lambda a: fields(a, checks),
            answer=ans,
            answer_hint="a JSON object " + hint + " with integers",
            budget=6,
            wrong=[{**ans, "modulus": prod}] if prod != L else [{**ans, "x": x + L}],
        )


# ---------------------------------------------------------------- logic grid
PEOPLE = ["Abena", "Bruno", "Chidi", "Dana", "Elif", "Farah", "Goran", "Hana"]
ATTRS = {
    "drink": ["tea", "coffee", "juice", "water", "cocoa"],
    "city": ["Accra", "Lima", "Oslo", "Pune", "Quito"],
    "pet": ["cat", "dog", "fish", "owl", "hamster"],
}


def _clue_true(clue, sol, order):
    kind = clue[0]
    if kind == "is":
        _, p, at, v = clue
        return sol[at][p] == v
    if kind == "not":
        _, p, at, v = clue
        return sol[at][p] != v
    if kind == "same":
        _, at1, v1, at2, v2 = clue
        p = [q for q in order if sol[at1][q] == v1][0]
        return sol[at2][p] == v2
    if kind == "left":  # seat of the v1 person is directly left of the v2 person
        _, at1, v1, at2, v2 = clue
        p1 = [q for q in order if sol[at1][q] == v1][0]
        p2 = [q for q in order if sol[at2][q] == v2][0]
        return order.index(p1) + 1 == order.index(p2)
    return False


def _clue_text(clue):
    kind = clue[0]
    if kind == "is":
        return f"{clue[1]}'s {clue[2]} is {clue[3]}."
    if kind == "not":
        return f"{clue[1]}'s {clue[2]} is not {clue[3]}."
    if kind == "same":
        return f"The person whose {clue[1]} is {clue[2]} has {clue[3]} {clue[4]}."
    return f"The person whose {clue[1]} is {clue[2]} sits directly left of the person whose {clue[3]} is {clue[4]}."


class LogicGrid:
    NAME = "logic-grid"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        n = 4
        attrs = ["drink", "city"] if level == 1 else ["drink", "city", "pet"]
        people = rng.sample(PEOPLE, n)
        order = sorted(people, key=lambda p: rng.random())  # seating order, left to right
        vals = {at: rng.sample(ATTRS[at], n) for at in attrs}
        sol = {at: dict(zip(order, vals[at])) for at in attrs}
        perms = {at: list(itertools.permutations(vals[at])) for at in attrs}
        cands = []
        for combo in itertools.product(*[perms[at] for at in attrs]):
            cands.append({at: dict(zip(order, combo[i])) for i, at in enumerate(attrs)})

        def random_clue():
            kind = rng.choice(["not", "not", "same", "same", "left", "is"])
            if kind in ("is", "not"):
                p = rng.choice(order)
                at = rng.choice(attrs)
                v = sol[at][p] if kind == "is" else rng.choice([x for x in vals[at] if x != sol[at][p]])
                return (kind, p, at, v)
            at1, at2 = rng.sample(attrs, 2)
            if kind == "same":
                p = rng.choice(order)
                return ("same", at1, sol[at1][p], at2, sol[at2][p])
            i = rng.randrange(n - 1)
            return ("left", at1, sol[at1][order[i]], at2, sol[at2][order[i + 1]])

        clues = []
        alive = cands
        guard = 0
        while len(alive) > 1 and guard < 400:
            guard += 1
            c = random_clue()
            if c in clues or c[0] == "is" and sum(1 for x in clues if x[0] == "is") >= 1:
                continue
            nxt = [s for s in alive if _clue_true(c, s, order)]
            if len(nxt) < len(alive):
                clues.append(c)
                alive = nxt
        if len(alive) != 1 or len(clues) < 4:
            return LogicGrid.build(level, rng)
        # drop redundant clues to make it tighter
        for c in list(clues):
            rest = [x for x in clues if x != c]
            if sum(1 for s in cands if all(_clue_true(x, s, order) for x in rest)) == 1:
                clues = rest
        rng.shuffle(clues)
        ask_at = attrs[-1]
        puzzle = [f"{n} people sit in a row, left to right: " + ", ".join(order) + ".",
                  "Each has a different " + " and a different ".join(attrs) + ".",
                  "Options: " + "; ".join(f"{at}: {', '.join(sorted(vals[at]))}" for at in attrs) + ".",
                  "Clues:"] + [f"{i + 1}. {_clue_text(c)}" for i, c in enumerate(clues)]
        target = sol[ask_at]

        def check(a):
            a = load(a)
            if not isinstance(a, dict):
                return 0.0
            norm = {str(k).strip().lower(): v for k, v in a.items()}
            if len(norm) != n:
                return 0.0
            for p in order:
                if p.lower() not in norm or same_text(norm[p.lower()], target[p]) != 1.0:
                    return 0.0
            return 1.0

        wrong = dict(target)
        a, b = rng.sample(order, 2)
        wrong[a], wrong[b] = wrong[b], wrong[a]
        return Built(
            question=f"Solve the puzzle in puzzle.txt. Give each person's {ask_at}.",
            files={"puzzle.txt": "\n".join(puzzle) + "\n"},
            check=check,
            answer=dict(target),
            answer_hint='a JSON object mapping every person to a value, e.g. {"' + order[0] + '": "' + vals[ask_at][0] + '", ...}',
            budget=8,
            wrong=[wrong],
        )


# ---------------------------------------------------------------- shortest route
class ShortestRoute:
    NAME = "shortest-route"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        n = rng.randint(9, 13)
        nodes = [chr(65 + i) for i in range(n)]
        edges = {}
        for i in range(1, n):
            j = rng.randrange(i)
            edges[tuple(sorted((nodes[i], nodes[j])))] = rng.randint(2, 20)
        for _ in range(n + rng.randint(2, 8)):
            a, b = rng.sample(nodes, 2)
            edges.setdefault(tuple(sorted((a, b))), rng.randint(2, 20))
        src, dst = rng.sample(nodes, 2)
        closed = []
        via = None
        if level == 2:
            closed = rng.sample(sorted(edges), 2)
            via = rng.choice([x for x in nodes if x not in (src, dst)])
        live = {e: w for e, w in edges.items() if e not in closed}
        adj = {v: [] for v in nodes}
        for (a, b), w in live.items():
            adj[a].append((b, w))
            adj[b].append((a, w))

        def dijkstra(s, t):
            # returns (cost, number of shortest paths, path)
            dist = {s: 0}
            cnt = {s: 1}
            prev = {}
            pq = [(0, s)]
            done = set()
            while pq:
                d, u = heapq.heappop(pq)
                if u in done:
                    continue
                done.add(u)
                for v, w in adj[u]:
                    nd = d + w
                    if v not in dist or nd < dist[v]:
                        dist[v], cnt[v], prev[v] = nd, cnt[u], u
                        heapq.heappush(pq, (nd, v))
                    elif nd == dist[v]:
                        cnt[v] += cnt[u]
            if t not in dist:
                return None
            path = [t]
            while path[-1] != s:
                path.append(prev[path[-1]])
            return dist[t], cnt[t], path[::-1]

        if level == 1:
            r = dijkstra(src, dst)
            if not r or r[1] != 1 or len(r[2]) < 4:
                return ShortestRoute.build(level, rng)
            cost, path = r[0], r[2]
        else:
            r1, r2 = dijkstra(src, via), dijkstra(via, dst)
            if not r1 or not r2 or r1[1] != 1 or r2[1] != 1:
                return ShortestRoute.build(level, rng)
            cost, path = r1[0] + r2[0], r1[2] + r2[2][1:]
            if len(set(path)) != len(path):
                return ShortestRoute.build(level, rng)
        rows = ["from,to,minutes"] + [f"{a},{b},{w}" for (a, b), w in sorted(edges.items(), key=lambda kv: rng.random())]
        files = {"roads.csv": "\n".join(rows) + "\n"}
        q = f"Roads in roads.csv are two-way. Find the fastest route from {src} to {dst}"
        if level == 2:
            files["notice.txt"] = ("Road works notice\nClosed today in both directions: " +
                                   "; ".join(f"{a}-{b}" for a, b in closed) + ".\n")
            q += f" that passes through {via}, avoiding closed roads (see notice.txt)"
        q += ". Give the total minutes and the route as a list of nodes, start and end included."
        wrong_cost = cost + 1
        return Built(
            question=q,
            files=files,
            check=lambda a: fields(a, {"minutes": lambda v: exact_int(v, cost),
                                       "route": lambda v: same_list(v, path, ordered=True)}),
            answer={"minutes": cost, "route": path},
            answer_hint='a JSON object {"minutes": 37, "route": ["A", "D", "C"]}',
            budget=8,
            wrong=[{"minutes": wrong_cost, "route": path}, {"minutes": cost, "route": path[::-1]}],
        )


# ---------------------------------------------------------------- exact probability
def _reduced(v, p):
    import re
    if not isinstance(v, str):
        return 0.0
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", v)
    if not m:
        return 0.0
    a, b = int(m.group(1)), int(m.group(2))
    if b == 0 or math.gcd(a, b) != 1:
        return 0.0
    return 1.0 if Fraction(a, b) == p else 0.0


class ExactProbability:
    NAME = "exact-probability"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        if level == 1:
            k = rng.randint(3, 5)
            sides = rng.choice([6, 8, 10])
            s = rng.randint(k + 2, k * sides - 2)
            ways = sum(1 for roll in itertools.product(range(1, sides + 1), repeat=k) if sum(roll) == s)
            p = Fraction(ways, sides ** k)
            text = (f"Roll {k} fair {sides}-sided dice (faces 1 to {sides}). "
                    f"What is the probability that the faces sum to exactly {s}?")
            wrong = Fraction(ways + 1, sides ** k)
        else:
            colors = rng.sample(["red", "blue", "green", "white", "black"], 3)
            counts = [rng.randint(3, 9) for _ in colors]
            draw = rng.randint(4, 6)
            target = colors[0]
            need = rng.randint(2, min(counts[0], draw - 1))
            N = sum(counts)
            tot = math.comb(N, draw)
            fav = sum(math.comb(counts[0], j) * math.comb(N - counts[0], draw - j)
                      for j in range(need, min(counts[0], draw) + 1))
            p = Fraction(fav, tot)
            text = ("A bag holds " + ", ".join(f"{c} {col}" for c, col in zip(counts, colors)) +
                    f" marbles. Draw {draw} marbles without replacement. "
                    f"What is the probability of drawing at least {need} {target} marbles?")
            exact = Fraction(math.comb(counts[0], need) * math.comb(N - counts[0], draw - need), tot)
            wrong = exact if exact != p else p + Fraction(1, tot)
        return Built(
            question="Answer the question in problem.txt as an exact reduced fraction.",
            files={"problem.txt": text + "\n"},
            check=lambda a: fields(a, {"probability": lambda v: _reduced(v, p)}),
            answer={"probability": f"{p.numerator}/{p.denominator}"},
            answer_hint='a JSON object {"probability": "a/b"} with the fraction in lowest terms',
            budget=6,
            wrong=[{"probability": f"{wrong.numerator}/{wrong.denominator}"},
                   {"probability": f"{p.numerator * 2}/{p.denominator * 2}"}],
        )
