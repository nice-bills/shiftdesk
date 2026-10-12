"""Industrial and physical systems v3 families: BOM explosion and tank level balance."""
import math

from ..grading import close, exact_int, fields, load, same_text
from .base import Built

DOMAIN = "industrial-physical-systems"


class BomExplosion:
    NAME = "bom-explosion"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        top = f"ASM-{rng.randint(100, 999)}"
        subs = [f"SUB-{c}" for c in rng.sample("ABCDEFGH", rng.randint(2, 3))]
        raws = [f"RM-{n}" for n in rng.sample(range(10, 99), rng.randint(4, 6))]
        bom = []  # parent, child, qty, scrap_pct
        for s in subs:
            bom.append((top, s, rng.randint(1, 4), 0))
        for r in rng.sample(raws, 2):
            bom.append((top, r, rng.randint(1, 6), rng.choice([0, 5, 10]) if level == 2 else 0))
        for s in subs:
            for r in rng.sample(raws, rng.randint(2, 3)):
                bom.append((s, r, rng.randint(1, 8), rng.choice([0, 0, 2, 5, 8]) if level == 2 else 0))
        units = rng.randrange(20, 400, 10)
        onhand = {}
        if level == 2:
            for s in rng.sample(subs, 1):
                onhand[s] = rng.randint(5, units // 2)
            for r in rng.sample(raws, 2):
                onhand[r] = rng.randint(10, 300)

        def explode(use_onhand, use_scrap):
            need = {}

            def add(part, qty):
                if use_onhand and part in onhand_left:
                    take = min(onhand_left[part], qty)
                    onhand_left[part] -= take
                    qty -= take
                if qty <= 0:
                    return
                children = [b for b in bom if b[0] == part]
                if not children:
                    need[part] = need.get(part, 0) + qty
                    return
                for _, child, q, sc in children:
                    gross = q * qty * (1 + (sc / 100 if use_scrap else 0))
                    add(child, math.ceil(gross - 1e-9))
            onhand_left = dict(onhand) if use_onhand else {}
            for _, child, q, sc in [b for b in bom if b[0] == top]:
                gross = q * units * (1 + (sc / 100 if use_scrap else 0))
                add(child, math.ceil(gross - 1e-9))
            return need

        need = explode(level == 2, level == 2)
        naive = explode(False, False)
        if level == 2 and naive == need:
            return BomExplosion.build(level, rng)
        if any(v <= 0 for v in need.values()) or not need:
            return BomExplosion.build(level, rng)
        rows = ["parent,child,qty_per_parent" + (",scrap_pct" if level == 2 else "")]
        rows += [f"{p},{c},{q}" + (f",{s}" if level == 2 else "") for p, c, q, s in sorted(bom, key=lambda b: rng.random())]
        order = [f"Work order WO-{rng.randint(1000, 9999)}: build {units} x {top}."]
        rules = ["Planning rules"]
        if level == 2:
            rules += ["- Gross quantity of a child = qty_per_parent x parent quantity x (1 + scrap_pct/100), "
                      "rounded UP to a whole unit, computed separately for each BOM line.",
                      "- Net each part against stock on hand (stock.csv) before exploding it further; a sub-assembly "
                      "taken from stock needs no components.",
                      "- Report only parts that have no BOM of their own (raw materials) that must still be bought."]
            files_stock = "part,on_hand\n" + "".join(f"{k},{v}\n" for k, v in onhand.items())
        else:
            rules += ["- Report total quantity of every raw material (a part with no BOM lines of its own)."]
        files = {"bom.csv": "\n".join(rows) + "\n", "work_order.txt": "\n".join(order + rules) + "\n"}
        if level == 2:
            files["stock.csv"] = files_stock
        target = {k: v for k, v in need.items() if v > 0}

        def check(a):
            a = load(a)
            if isinstance(a, dict) and len(a) == 1 and isinstance(load(next(iter(a.values()))), dict):
                a = load(next(iter(a.values())))
            if not isinstance(a, dict):
                return 0.0
            got = {str(k).strip().upper(): v for k, v in a.items()}
            got = {k: v for k, v in got.items() if not (isinstance(v, (int, float)) and v == 0)}
            if set(got) != set(target):
                return 0.0
            return 1.0 if all(exact_int(got[k], target[k]) == 1.0 for k in target) else 0.0

        return Built(
            question=("Explode the work order through bom.csv. How many units of each raw material are required"
                      + (" to buy" if level == 2 else "") + "?"),
            files=files,
            check=check,
            answer=dict(sorted(target.items())),
            answer_hint='a JSON object mapping each raw material id to an integer, e.g. {"RM-12": 340, "RM-40": 95}',
            budget=8,
            wrong=[dict(sorted(naive.items()))] if level == 2 else [{k: v + 1 for k, v in target.items()}],
        )


class TankBalance:
    NAME = "tank-balance"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        cap = rng.choice([8000, 10000, 12000, 15000])
        level0 = rng.randint(int(cap * 0.2), int(cap * 0.5))
        alarm = int(cap * rng.choice([0.8, 0.85, 0.9]))
        t = 6 * 60
        segs = []
        for i in range(rng.randint(6, 9)):
            dur = rng.choice([15, 20, 30, 45, 60])
            inflow = rng.choice([0, 40, 60, 80, 120, 150])
            outflow = rng.choice([0, 20, 50, 70, 100])
            segs.append([t, t + dur, inflow, outflow])
            t += dur
        offline = None
        if level == 2:
            offline = rng.choice(segs)
        lvl = level0
        first_alarm = None
        overflow = 0.0
        for s in segs:
            out = 0 if s is offline else s[3]
            rate = s[2] - out
            dur = s[1] - s[0]
            end = lvl + rate * dur
            if first_alarm is None and rate > 0 and lvl < alarm <= end:
                first_alarm = s[0] + (alarm - lvl) / rate
            if level == 2 and end > cap:
                overflow += end - cap
                end = cap
            lvl = max(0.0, end) if level == 2 else end
        if level == 1 and not (0 <= lvl <= cap):
            return TankBalance.build(level, rng)
        if first_alarm is None:
            return TankBalance.build(level, rng)
        fa = math.ceil(first_alarm - 1e-9)
        fa_s = f"{fa // 60:02d}:{fa % 60:02d}"
        rows = ["start,end,inflow_l_per_min,outflow_l_per_min"]
        rows += [f"{s[0] // 60:02d}:{s[0] % 60:02d},{s[1] // 60:02d}:{s[1] % 60:02d},{s[2]},{s[3]}" for s in segs]
        spec = [f"Tank T-{rng.randint(1, 9)}: capacity {cap} L, level at 06:00 was {level0} L.",
                f"High-level alarm at {alarm} L. Flows are constant within each row."]
        if level == 2:
            spec.append("If the tank is full, extra inflow goes to the overflow drain and the level stays at capacity. "
                        "Level cannot go below 0.")
        files = {"flows.csv": "\n".join(rows) + "\n", "tank.txt": "\n".join(spec) + "\n"}
        if level == 2:
            files["shift_log.txt"] = (f"Operator log: discharge pump was tripped from "
                                      f"{offline[0] // 60:02d}:{offline[0] % 60:02d} to "
                                      f"{offline[1] // 60:02d}:{offline[1] % 60:02d}; outflow in that row did not happen.\n")
        end_t = segs[-1][1]
        q = (f"What is the tank level in litres at {end_t // 60:02d}:{end_t % 60:02d}, and at what time (HH:MM, "
             "rounded up to the whole minute) does the level first reach the alarm level?")
        return Built(
            question=q,
            files=files,
            check=lambda a: fields(a, {"final_level_l": lambda v: close(v, lvl, abs_tol=0.5),
                                       "first_alarm": lambda v: same_text(v, fa_s)}),
            answer={"final_level_l": round(lvl, 1), "first_alarm": fa_s},
            answer_hint='a JSON object {"final_level_l": 7350, "first_alarm": "08:47"}',
            budget=8,
            wrong=[{"final_level_l": round(lvl + 100, 1), "first_alarm": fa_s}],
        )
