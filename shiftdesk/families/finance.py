"""Finance v3 families: NPV choice, bond pricing, FIFO cost basis."""
from ..grading import close, exact_int, fields, same_text
from .base import Built

DOMAIN = "finance-economics"


def _npv(rate, flows):
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(flows))


class NpvChoice:
    NAME = "npv-choice"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        while True:
            n = rng.randint(3, 5)
            years = rng.randint(4, 6)
            ids = [f"P{i}" for i in rng.sample(range(10, 99), n)]
            projects = {}
            risk = {}
            for pid in ids:
                capex = -rng.randrange(200, 900, 10) * 1000
                flows = [capex] + [rng.randrange(40, 320, 5) * 1000 for _ in range(years)]
                projects[pid] = flows
                risk[pid] = rng.choice(["low", "medium", "high"])
            rates = {"low": 0.07, "medium": 0.095, "high": 0.13} if level == 2 else None
            base = rng.choice([0.06, 0.08, 0.1])
            errata = None
            final = {k: list(v) for k, v in projects.items()}
            if level == 2:
                pid = rng.choice(ids)
                yr = rng.randint(1, years)
                newv = rng.randrange(40, 320, 5) * 1000
                errata = (pid, yr, newv)
                final[pid][yr] = newv

            def rate_of(pid):
                return rates[risk[pid]] if level == 2 else base

            npvs = {pid: _npv(rate_of(pid), fl) for pid, fl in final.items()}
            best = max(npvs, key=npvs.get)
            ordered = sorted(npvs.values(), reverse=True)
            if npvs[best] <= 0 or ordered[0] - ordered[1] < 3000:
                continue
            if level == 2:
                naive = {pid: _npv(0.095, fl) for pid, fl in projects.items()}
                nbest = max(naive, key=naive.get)
                if nbest == best and abs(naive[nbest] - npvs[best]) < 2:
                    continue
                wrong = {"best_project": nbest, "npv": round(naive[nbest], 2)}
            else:
                wrong = {"best_project": best, "npv": round(sum(final[best]), 2)}
            break
        head = "project,risk_class," + ",".join(f"y{t}" for t in range(years + 1))
        rows = [head] + [f"{pid},{risk[pid]}," + ",".join(str(x) for x in projects[pid]) for pid in ids]
        memo = ["Capital committee memo", "Cash flows are in USD at the end of each year; y0 is the upfront investment."]
        if level == 1:
            memo.append(f"Discount every project at {base * 100:g}% per year.")
        else:
            memo.append("Discount rate depends on risk class: low 7%, medium 9.5%, high 13% per year.")
            memo += ["", f"Errata (finance team): {errata[0]} y{errata[1]} should read {errata[2]}. "
                         "The CSV was not updated."]
        files = {"projects.csv": "\n".join(rows) + "\n", "memo.txt": "\n".join(memo) + "\n"}
        return Built(
            question="Which project has the highest net present value, and what is that NPV in USD?",
            files=files,
            check=lambda a: fields(a, {"best_project": lambda v: same_text(v, best),
                                       "npv": lambda v: close(v, npvs[best], abs_tol=1.0)}),
            answer={"best_project": best, "npv": round(npvs[best], 2)},
            answer_hint='a JSON object {"best_project": "P00", "npv": 123456.78} (NPV within 1 USD)',
            budget=8,
            wrong=[wrong],
        )


class BondDesk:
    NAME = "bond-desk"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        bonds = []
        for i in range(rng.randint(3, 5)):
            bonds.append({
                "id": f"BD{rng.randint(100, 999)}",
                "face": rng.choice([100, 1000]),
                "coupon": rng.choice([2.5, 3.0, 3.75, 4.25, 5.0, 5.5, 6.125, 7.0]),
                "freq": rng.choice([1, 2]),
                "years": rng.randint(2, 12),
                "ytm": round(rng.uniform(2.0, 8.0), 2),
            })
        ids = [b["id"] for b in bonds]
        if len(set(ids)) != len(ids):
            return BondDesk.build(level, rng)
        tb = rng.choice(bonds)
        f, n = tb["freq"], tb["years"] * tb["freq"]
        c = tb["face"] * tb["coupon"] / 100 / f
        y = tb["ytm"] / 100 / f
        cfs = [(t, c + (tb["face"] if t == n else 0)) for t in range(1, n + 1)]
        price = sum(cf / (1 + y) ** t for t, cf in cfs)
        mac = sum(t / f * cf / (1 + y) ** t for t, cf in cfs) / price
        mod = mac / (1 + y)
        annual_price = sum((tb["face"] * tb["coupon"] / 100 + (tb["face"] if t == tb["years"] else 0)) /
                           (1 + tb["ytm"] / 100) ** t for t in range(1, tb["years"] + 1))
        rows = ["bond_id,face,coupon_pct,coupons_per_year,years_to_maturity,ytm_pct"]
        rows += [f"{b['id']},{b['face']},{b['coupon']},{b['freq']},{b['years']},{b['ytm']}" for b in bonds]
        conv = ("Conventions: price on a coupon date (no accrued interest). YTM is quoted as a nominal annual rate "
                "compounded at the coupon frequency, so the per-period rate is ytm/coupons_per_year. "
                "Macaulay duration is in years; modified duration = Macaulay / (1 + ytm/coupons_per_year).\n")
        files = {"bonds.csv": "\n".join(rows) + "\n", "conventions.txt": conv}
        if level == 1:
            checks = {"price": lambda v: close(v, price, abs_tol=0.01 * tb["face"] / 100)}
            ans = {"price": round(price, 4)}
            hint = '{"price": 101.2345} (within 0.01 per 100 face)'
            q = f"What is the price of bond {tb['id']} per its full face value?"
            far = abs(annual_price - price) > 0.05 * tb["face"] / 100
            wrong = [{"price": round(annual_price, 4)}] if f == 2 and far else [{"price": round(price * 1.01, 4)}]
        else:
            checks = {"price": lambda v: close(v, price, abs_tol=0.01 * tb["face"] / 100),
                      "modified_duration": lambda v: close(v, mod, abs_tol=0.005)}
            ans = {"price": round(price, 4), "modified_duration": round(mod, 4)}
            hint = '{"price": 101.2345, "modified_duration": 4.5678} (price within 0.01 per 100 face, duration within 0.005)'
            q = f"For bond {tb['id']}, give its price per full face value and its modified duration in years."
            wrong = [{"price": round(price, 4), "modified_duration": round(mac, 4)}]
        return Built(question=q, files=files, check=lambda a: fields(a, checks), answer=ans,
                     answer_hint="a JSON object " + hint, budget=8, wrong=wrong)


class FifoBasis:
    NAME = "fifo-basis"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        tick = rng.choice(["ACME", "BLUE", "KORA", "NOVA", "ZENO"])
        other = rng.choice([t for t in ["ACME", "BLUE", "KORA", "NOVA", "ZENO"] if t != tick])
        rows = []
        lots = []  # [qty, unit_cost]
        realized = 0.0
        avg_wrong = [0.0, 0.0]  # qty, cost for average-cost wrong answer
        avg_real = 0.0
        day = 2
        split_done = False
        fee_total = 0.0
        for k in range(rng.randint(7, 11)):
            day += rng.randint(1, 9)
            date = f"2026-{1 + day // 28:02d}-{1 + day % 28:02d}"
            held = sum(q for q, _ in lots)
            if level == 2 and not split_done and k >= 3 and rng.random() < 0.4:
                ratio = rng.choice([2, 3])
                rows.append([date, "SPLIT", tick, ratio, "", ""])
                lots = [[q * ratio, cst / ratio] for q, cst in lots]
                avg_wrong = [avg_wrong[0] * ratio, avg_wrong[1]]
                split_done = True
                continue
            if held >= 20 and rng.random() < 0.45:
                qty = rng.randint(5, held)
                px = round(rng.uniform(20, 90), 2)
                fee = round(rng.uniform(1, 9), 2) if level == 2 else 0.0
                rows.append([date, "SELL", tick, qty, px, fee])
                left = qty
                cost = 0.0
                while left:
                    take = min(left, lots[0][0])
                    cost += take * lots[0][1]
                    lots[0][0] -= take
                    left -= take
                    if lots[0][0] == 0:
                        lots.pop(0)
                realized += qty * px - fee - cost
                avg_unit = avg_wrong[1] / avg_wrong[0]
                avg_real += qty * px - fee - qty * avg_unit
                avg_wrong = [avg_wrong[0] - qty, avg_wrong[1] - qty * avg_unit]
            else:
                qty = rng.randint(10, 80)
                px = round(rng.uniform(20, 90), 2)
                fee = round(rng.uniform(1, 9), 2) if level == 2 else 0.0
                rows.append([date, "BUY", tick, qty, px, fee])
                unit = (qty * px + fee) / qty
                lots.append([qty, unit])
                avg_wrong = [avg_wrong[0] + qty, avg_wrong[1] + qty * px + fee]
            if rng.random() < 0.3:
                rows.append([date, rng.choice(["BUY", "SELL"]), other, rng.randint(5, 40), round(rng.uniform(10, 50), 2), 0])
        if not any(r[1] == "SELL" and r[2] == tick for r in rows) or abs(realized - avg_real) < 1:
            return FifoBasis.build(level, rng)
        shares = sum(q for q, _ in lots)
        txt = "date,action,ticker,quantity,price,fee\n" + "".join(",".join(str(x) for x in r) + "\n" for r in rows)
        pol = ["Tax lot policy", "- Lots are relieved first-in, first-out (FIFO)."]
        if level == 2:
            pol += ["- Buy fees are added to that lot's cost basis; sell fees reduce the sale proceeds.",
                    "- A SPLIT row with quantity r multiplies every open lot's share count by r and divides its unit cost by r."]
        else:
            pol += ["- The fee column is zero in this account."]
        files = {"trades.csv": txt, "policy.txt": "\n".join(pol) + "\n"}
        return Built(
            question=f"For {tick} only: what is the total realized gain (USD) and how many shares are still held?",
            files=files,
            check=lambda a: fields(a, {"realized_gain": lambda v: close(v, realized, abs_tol=0.02),
                                       "shares_held": lambda v: exact_int(v, shares)}),
            answer={"realized_gain": round(realized, 2), "shares_held": shares},
            answer_hint='a JSON object {"realized_gain": -123.45, "shares_held": 40} (gain within 0.02)',
            budget=8,
            wrong=[{"realized_gain": round(avg_real, 2), "shares_held": shares}],
        )
