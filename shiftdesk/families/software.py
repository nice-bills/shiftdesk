"""Software engineering v3 families: change impact and dependency version resolution."""
import json

from ..grading import fields, load, same_list, same_text
from .base import Built

DOMAIN = "software-engineering"


class ChangeImpact:
    NAME = "change-impact"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        n = rng.randint(7, 10)
        mods = sorted(rng.sample(["auth", "billing", "cache", "core", "db", "events", "gateway", "mailer",
                                  "metrics", "orders", "search", "ui", "users", "web"], n))
        order = list(mods)
        rng.shuffle(order)  # a hidden topological order: deps come earlier
        deps = {m: [] for m in mods}
        for i, m in enumerate(order):
            if i:
                deps[m] = sorted(rng.sample(order[:i], rng.randint(0, min(3, i))))
        changed = sorted(rng.sample(mods, 1 if level == 1 else 2))
        dev_only = set()
        if level == 2:
            # some dependency edges are dev-only (tests), they do not propagate rebuilds
            edges = [(m, d) for m in mods for d in deps[m]]
            for e in rng.sample(edges, min(3, len(edges))):
                dev_only.add(e)
        consumers = {m: [] for m in mods}
        for m in mods:
            for d in deps[m]:
                if (m, d) not in dev_only:
                    consumers[d].append(m)
        aff = set(changed)
        stack = list(changed)
        while stack:
            x = stack.pop()
            for c in consumers[x]:
                if c not in aff:
                    aff.add(c)
                    stack.append(c)
        # build order: Kahn with lexicographically smallest eligible module
        build = []
        left = set(aff)
        while left:
            ready = sorted(m for m in left if not any(d in left and (m, d) not in dev_only for d in deps[m]))
            build.append(ready[0])
            left.remove(ready[0])
        aff_all = set(changed)
        stack = list(changed)
        while stack:
            x = stack.pop()
            for m in mods:
                if x in deps[m] and m not in aff_all:
                    aff_all.add(m)
                    stack.append(m)
        if len(aff) < 3 or (level == 2 and aff_all == aff) or build == sorted(aff):
            return ChangeImpact.build(level, rng)
        graph = {}
        for m in mods:
            if level == 2:
                graph[m] = {"deps": [d for d in deps[m] if (m, d) not in dev_only],
                            "dev_deps": [d for d in deps[m] if (m, d) in dev_only]}
            else:
                graph[m] = deps[m]
        files = {"modules.json": json.dumps(graph, indent=1) + "\n",
                 "change.txt": "Changed in this release: " + ", ".join(changed) + "\n",
                 "BUILD.md": ("Rebuild every changed module and every module that depends on one, directly or "
                              "transitively" + (" through `deps`. `dev_deps` are test-only and never trigger a rebuild "
                                                "or constrain build order" if level == 2 else "") +
                              ".\nBuild order: a module builds after all of its affected dependencies; when several "
                              "are ready, take the alphabetically first.\n")}
        return Built(
            question="Which modules must be rebuilt, and in what order?",
            files=files,
            check=lambda a: fields(a, {"rebuild": lambda v: same_list(v, sorted(aff)),
                                       "build_order": lambda v: same_list(v, build, ordered=True)}),
            answer={"rebuild": sorted(aff), "build_order": build},
            answer_hint='a JSON object {"rebuild": ["core", "web"], "build_order": ["core", "web"]}',
            budget=8,
            wrong=[{"rebuild": sorted(aff), "build_order": sorted(aff)}] if build != sorted(aff) else
                  [{"rebuild": sorted(aff_all | {mods[0]}), "build_order": build}],
        )


def _parse(v):
    return tuple(int(x) for x in v.split("."))


def _sat(ver, spec):
    v = _parse(ver)
    for part in spec.split(","):
        part = part.strip()
        if part.startswith("^"):
            b = _parse(part[1:])
            hi = (b[0] + 1, 0, 0) if b[0] > 0 else (0, b[1] + 1, 0)
            if not (b <= v < hi):
                return False
        elif part.startswith("~"):
            b = _parse(part[1:])
            if not (b <= v < (b[0], b[1] + 1, 0)):
                return False
        elif part.startswith(">="):
            if not v >= _parse(part[2:]):
                return False
        elif part.startswith("<"):
            if not v < _parse(part[1:]):
                return False
        elif part.startswith("=="):
            if v != _parse(part[2:]):
                return False
    return True


class VersionResolve:
    NAME = "version-resolve"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        pkgs = rng.sample(["requests", "lodash", "serde", "numpy", "react", "tokio", "flask", "axios"], 4)
        avail = {}
        for p in pkgs:
            vs = set()
            major = rng.randint(0, 3)
            for _ in range(rng.randint(8, 12)):
                vs.add(f"{rng.randint(max(0, major - 1), major + 1)}.{rng.randint(0, 12)}.{rng.randint(0, 9)}")
            avail[p] = sorted(vs, key=_parse)
        reqs = {}
        yanked = {}
        for p in pkgs:
            base = rng.choice(avail[p][: max(1, len(avail[p]) * 2 // 3)])
            kind = rng.choice(["^", "~", ">=,<"])
            if kind == ">=,<":
                b = _parse(base)
                spec = f">={base}, <{b[0] + 1}.0.0"
            else:
                spec = kind + base
            reqs[p] = [("app", spec)]
            app_ok = [v for v in avail[p] if _sat(v, spec)]
            if level == 2 and app_ok and rng.random() < 0.7:
                other = rng.choice(app_ok)
                b = _parse(other)
                reqs[p].append(("plugin", f"<{b[0]}.{b[1] + 1}.0"))
        if level == 2:
            for p in rng.sample(pkgs, 2):
                cands = [v for v in avail[p] if all(_sat(v, s) for _, s in reqs[p])]
                if len(cands) >= 2:
                    yanked[p] = cands[-1]
        picks = {}
        for p in pkgs:
            cands = [v for v in avail[p] if all(_sat(v, s) for _, s in reqs[p]) and yanked.get(p) != v]
            picks[p] = cands[-1] if cands else "none"
        naive = {}
        for p in pkgs:
            cands = [v for v in avail[p] if _sat(v, reqs[p][0][1])]
            naive[p] = cands[-1] if cands else "none"
        lex = {}
        for p in pkgs:
            cands = sorted([v for v in avail[p] if all(_sat(v, s) for _, s in reqs[p]) and yanked.get(p) != v])
            lex[p] = cands[-1] if cands else "none"
        if sum(v == "none" for v in picks.values()) > 1:
            return VersionResolve.build(level, rng)
        if (level == 2 and naive == picks) or (level == 1 and lex == picks) and rng.random() < 0.7:
            return VersionResolve.build(level, rng)
        index = {p: rng.sample(avail[p], len(avail[p])) for p in pkgs}  # registry lists versions unordered
        files = {"registry.json": json.dumps(index, indent=1) + "\n",
                 "requirements.txt": "".join(f"{p} {s}    # required by {who}\n" for p in pkgs for who, s in reqs[p]),
                 "RESOLVER.md": ("For each package pick the highest available version that satisfies every requirement "
                                 "line for it. Versions compare numerically by major, minor, patch.\n"
                                 "^X.Y.Z means >=X.Y.Z and <(X+1).0.0 (for X=0: <0.(Y+1).0). ~X.Y.Z means >=X.Y.Z and "
                                 "<X.(Y+1).0. If nothing satisfies, write \"none\".\n")}
        if level == 2:
            files["advisory.txt"] = ("Yanked releases (never install): " + ", ".join(f"{p}=={v}" for p, v in yanked.items()) + "\n")

        def check(a):
            a = load(a)
            if not isinstance(a, dict):
                return 0.0
            if len(a) == 1 and isinstance(load(next(iter(a.values()))), dict):
                a = load(next(iter(a.values())))
            got = {str(k).strip().lower(): v for k, v in a.items()}
            if set(got) != set(picks):
                return 0.0
            return 1.0 if all(same_text(got[p], picks[p]) == 1.0 for p in picks) else 0.0

        return Built(
            question="Resolve one version for each package in requirements.txt using registry.json.",
            files=files,
            check=check,
            answer=dict(picks),
            answer_hint='a JSON object mapping every package to a version string, e.g. {"flask": "2.3.1", "axios": "none"}',
            budget=8,
            wrong=[dict(naive)] if naive != picks else [{**picks, pkgs[0]: avail[pkgs[0]][0] if avail[pkgs[0]][0] != picks[pkgs[0]] else "none"}],
        )
