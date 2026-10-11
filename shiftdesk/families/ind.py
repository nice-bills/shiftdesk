"""Industrial: availability and OEE from a machine state log."""
from ..grading import close, same_text
from .base import Built

DOMAIN = "industrial-physical-systems"
NAME = "line-oee"

SHIFT_START = 6 * 60  # 06:00
SHIFT_MIN = 480


def _clock(minute):
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _machine_timeline(rng, breaks):
    """Intervals (start, end, state) covering the shift. Breaks are BREAK."""
    cuts = []
    t = 0
    for b0, b1 in breaks:
        cuts.append((t, b0))
        cuts.append((b0, b1, "BREAK"))
        t = b1
    cuts.append((t, SHIFT_MIN))
    out = []
    for seg in cuts:
        if len(seg) == 3:
            out.append(seg)
            continue
        a, b = seg
        t = a
        while t < b:
            state = rng.choices(["RUN", "DOWN", "IDLE"], [0.7, 0.18, 0.12])[0]
            length = rng.randint(8, 70) if state == "RUN" else rng.randint(3, 30)
            end = min(b, t + length)
            if out and out[-1][2] == state and out[-1][1] == t:
                out[-1] = (out[-1][0], end, state)
            else:
                out.append((t, end, state))
            t = end
    return out


def build(level, rng):
    n_machines = {1: 3, 2: 4, 3: 6}[level]
    machines = [f"M{i}" for i in rng.sample(range(10, 60), n_machines)]
    breaks = [] if level == 1 else [(150, 165), (270, 300)] if level == 3 else [(240, 270)]
    events = []
    stats = {}
    for m in machines:
        tl = _machine_timeline(rng, breaks)
        run = sum(b - a for a, b, s in tl if s == "RUN")
        planned = SHIFT_MIN - sum(b - a for a, b, s in tl if s == "BREAK")
        stats[m] = {"run": run, "planned": planned}
        for a, b, s in tl:
            events.append((a, m, s))
    events.sort(key=lambda e: (e[0], e[1]))
    log = ["time,machine,state"] + [f"{_clock(SHIFT_START + a)},{m},{s}" for a, m, s in events]
    log_text = "\n".join(log) + "\n"
    note = (
        f"Shift runs 06:00 to 14:00. Each row is a state change; a state lasts until that machine's next row "
        f"or the end of the shift.\n"
    )
    if level == 1:
        m = rng.choice(machines)
        target = round(100 * stats[m]["run"] / SHIFT_MIN, 1)
        return Built(
            question=(
                f"From states.csv and notes.txt: what was the availability of machine {m} this shift, "
                f"as a percent of the 480 planned minutes spent in RUN? Round to 1 decimal."
            ),
            files={"states.csv": log_text, "notes.txt": note},
            check=lambda a: close(a, target, abs_tol=0.11),
            answer=target,
            answer_hint="a number such as 73.5",
            budget=8,
            wrong=[round(100 * sum(1 for e in events if e[1] == m and e[2] == "RUN") / len(events), 1)],
        )
    prod = ["machine,ideal_cycle_s,total_parts,good_parts"]
    oee = {}
    for m in machines:
        cycle = rng.choice([12, 15, 18, 20, 24, 30, 36, 45])
        cap = stats[m]["run"] * 60 // cycle
        total = rng.randint(int(cap * 0.7), max(int(cap * 0.7) + 1, cap))
        good = total - rng.randint(0, max(1, total // 12))
        prod.append(f"{m},{cycle},{total},{good}")
        oee[m] = 100 * (cycle * good) / (stats[m]["planned"] * 60)
    note += (
        "Planned time is the shift minus BREAK time. OEE = availability x performance x quality, where "
        "availability = RUN time / planned time, performance = ideal_cycle_s x total_parts / RUN time, "
        "quality = good_parts / total_parts.\n"
    )
    files = {"states.csv": log_text, "notes.txt": note, "production.csv": "\n".join(prod) + "\n"}
    if level == 2:
        m = rng.choice(machines)
        target = round(oee[m], 1)
        naive = round(oee[m] * stats[m]["planned"] / SHIFT_MIN, 1)
        return Built(
            question=f"What was the OEE of machine {m} this shift, in percent? Round to 1 decimal.",
            files=files,
            check=lambda a: close(a, target, abs_tol=0.11),
            answer=target,
            answer_hint="a number such as 61.2",
            budget=10,
            wrong=[naive],
        )
    worst = min(oee, key=oee.get)
    target = f"{worst} {oee[worst]:.1f}"

    def check(a, worst=worst, value=oee[worst]):
        if isinstance(a, dict):
            ids = [v for v in a.values() if isinstance(v, str) and v.strip().upper() == worst]
            nums = [v for v in a.values() if not isinstance(v, str) or v.strip().upper() != worst]
            if len(ids) == 1 and len(nums) == 1:
                return close(nums[0], round(value, 1), abs_tol=0.11)
            return 0.0
        if not isinstance(a, str):
            return 0.0
        parts = a.replace(",", " ").split()
        if len(parts) != 2 or parts[0].upper() != worst:
            return 0.0
        return close(parts[1], round(value, 1), abs_tol=0.11)

    best = max(oee, key=oee.get)
    return Built(
        question=(
            "Which machine had the lowest OEE this shift, and what was it? Answer as the machine id, a space, "
            "and the OEE percent rounded to 1 decimal."
        ),
        files=files,
        check=check,
        answer=target,
        answer_hint='a string such as "M17 54.3"',
        budget=12,
        wrong=[f"{best} {oee[best]:.1f}"],
    )
