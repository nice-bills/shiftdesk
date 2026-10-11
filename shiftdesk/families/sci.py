"""Natural science: reaction kinetics from noisy concentration data."""
import math

from ..grading import close, same_text
from .base import Built

DOMAIN = "natural-science"
NAME = "kinetics-lab"


def _fit(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    icpt = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (icpt + slope * x)) ** 2 for x, y in zip(xs, ys))
    return slope, icpt, 1 - ss_res / ss_tot


def _conc(order, c0, k, t):
    if order == 0:
        return c0 - k * t
    if order == 1:
        return c0 * math.exp(-k * t)
    return 1 / (1 / c0 + k * t)


def build(level, rng):
    c0 = round(rng.uniform(0.4, 2.0), 3)
    if level < 3:
        order = 1
        k = rng.uniform(0.01, 0.12)  # per minute
    else:
        order = rng.choice([0, 1, 2])
        k = {0: rng.uniform(0.003, 0.012), 1: rng.uniform(0.01, 0.08), 2: rng.uniform(0.02, 0.15)}[order]
    t_end = {0: 0.8 * c0 / k, 1: 2.5 / k, 2: 6 / (k * c0)}[order]
    n = {1: 10, 2: 14, 3: 16}[level]
    times = sorted({round(t_end * i / (n - 1), 1) for i in range(n)})
    noise = 0.012
    rows = []
    for t in times:
        c = _conc(order, c0, k, t)
        c = max(c * (1 + rng.uniform(-noise, noise)), 1e-4)
        rows.append([t, round(c, 4), "OK"])
    unit = "min"
    if level >= 2:
        bad = rng.sample(range(1, len(rows) - 1), 2)
        for i in bad:
            rows[i][1] = round(rows[i][1] * rng.choice([0.4, 2.2]), 4)
            rows[i][2] = "FAIL"
        unit = "s"
    lines = [f"time_{unit},conc_mol_per_L,qc"]
    for t, c, q in rows:
        tv = round(t * 60) if unit == "s" else t
        lines.append(f"{tv},{c},{q}")
    files = {"run.csv": "\n".join(lines) + "\n"}
    good = [(t, c) for t, c, q in rows if q == "OK"]
    xs = [t for t, _ in good]
    if level == 1:
        slope, _, _ = _fit(xs, [math.log(c) for _, c in good])
        target = -slope
        files["protocol.txt"] = "First-order decay. Estimate k as minus the least-squares slope of ln(conc) against time.\n"
        two_point = math.log(good[0][1] / good[-1][1]) / (xs[-1] - xs[0])
        return Built(
            question="From run.csv and protocol.txt, what is the rate constant k in 1/min? Give 4 significant figures.",
            files=files,
            check=lambda a: close(a, target, rel=0.003),
            answer=round(target, 6),
            answer_hint="a number such as 0.04213",
            budget=8,
            wrong=[round(two_point * 1.02, 6), round(target * 60, 6)],
        )
    if level == 2:
        slope, _, _ = _fit(xs, [math.log(c) for _, c in good])
        target = math.log(2) / -slope
        files["protocol.txt"] = (
            "First-order decay. Drop rows whose qc is not OK. Estimate k as minus the least-squares slope of "
            "ln(conc) against time, then the half-life is ln(2)/k.\n"
        )
        allrows = [(t, c) for t, c, _ in rows]
        s_all, _, _ = _fit([t for t, _ in allrows], [math.log(c) for _, c in allrows])
        return Built(
            question="From run.csv and protocol.txt, what is the half-life in minutes? Give 4 significant figures.",
            files=files,
            check=lambda a: close(a, target, rel=0.003),
            answer=round(target, 5),
            answer_hint="a number such as 17.42",
            budget=10,
            wrong=[round(math.log(2) / -s_all, 5), round(target * 60, 5)],
        )
    fits = {
        0: _fit(xs, [c for _, c in good]),
        1: _fit(xs, [math.log(c) for _, c in good]),
        2: _fit(xs, [1 / c for _, c in good]),
    }
    best = max(fits, key=lambda o: fits[o][2])
    slope, icpt, _ = fits[best]
    if best == 0:
        kk, c0_fit = -slope, icpt
        half = c0_fit / (2 * kk)
    elif best == 1:
        kk = -slope
        half = math.log(2) / kk
    else:
        kk, c0_fit = slope, 1 / icpt
        half = 1 / (kk * c0_fit)
    files["protocol.txt"] = (
        "Order unknown (0, 1 or 2). Drop rows whose qc is not OK. Fit conc, ln(conc) and 1/conc against time by "
        "least squares; the order is the one whose fit has the highest R^2. For that order take k from the slope "
        "and the initial concentration from the fitted intercept, and report the first half-life measured from t=0 "
        "(zero order: C0/(2k); first: ln2/k; second: 1/(k*C0)).\n"
    )
    target = f"{best} {half:.4g}"

    def check(a, best=best, half=half):
        if isinstance(a, str):
            parts = a.replace(",", " ").split()
        elif isinstance(a, list):
            parts = a
        elif isinstance(a, dict):
            parts = list(a.values())
        else:
            return 0.0
        if len(parts) != 2:
            return 0.0
        try:
            if int(float(parts[0])) != best:
                return 0.0
        except (TypeError, ValueError):
            return 0.0
        return close(parts[1], half, rel=0.004)

    return Built(
        question=(
            "From run.csv and protocol.txt: what is the reaction order and the half-life in minutes? Answer as the "
            "order, a space, and the half-life to 4 significant figures."
        ),
        files=files,
        check=check,
        answer=target,
        answer_hint='a string such as "1 23.45"',
        budget=12,
        wrong=[f"{(best + 1) % 3} {half:.4g}"],
    )
