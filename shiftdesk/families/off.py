"""Office: expense reimbursement under a written policy."""
from ..grading import close
from .base import Built

DOMAIN = "office-white-collar"
NAME = "expense-policy"

NAMES = ["Ama Owusu", "Liam Chen", "Sofia Rossi", "Kwame Mensah", "Priya Nair", "Jonas Berg", "Lena Weiss", "Diego Ruiz"]
CATS = ["meal", "taxi", "hotel", "office_supplies", "alcohol", "airfare", "parking"]
RATES = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "GHS": 0.064}


def build(level, rng):
    people = rng.sample(NAMES, 4 if level == 1 else 6)
    who = people[0]
    month = rng.choice(["2026-03", "2026-04", "2026-05"])
    rows = []
    rid = 100
    days = [f"{month}-{d:02d}" for d in range(1, 29)]
    for person in people:
        for _ in range(rng.randint(8, 14) if person == who else rng.randint(4, 9)):
            rid += rng.randint(1, 4)
            cat = rng.choice(CATS)
            amt = round(rng.uniform(4, 60) if cat in ("meal", "taxi", "parking", "alcohol", "office_supplies") else rng.uniform(80, 420), 2)
            cur = "USD" if level == 1 else rng.choice(["USD", "USD", "EUR", "GBP", "GHS"])
            if cur == "GHS":
                amt = round(amt / RATES["GHS"], 2)
            elif cur != "USD":
                amt = round(amt / RATES[cur], 2)
            receipt = "yes" if level == 1 else rng.choice(["yes", "yes", "yes", "no"])
            rows.append([f"E{rid}", person, rng.choice(days), cat, amt, cur, receipt])
    if level == 3:
        mine = [r for r in rows if r[1] == who]
        for r in rng.sample(mine, 2):
            rid += 1
            rows.append([f"E{rid}"] + r[1:])
        meal_day = rng.choice(days)
        for _ in range(3):
            rid += 1
            rows.append([f"E{rid}", who, meal_day, "meal", round(rng.uniform(18, 35), 2), "USD", "yes"])
    rows.sort(key=lambda r: (r[2], r[0]))
    # a few rows from another month
    other = "2026-02" if month != "2026-02" else "2026-06"
    for _ in range(3):
        rid += 1
        rows.append([f"E{rid}", who, f"{other}-{rng.randint(1, 28):02d}", "taxi", round(rng.uniform(8, 40), 2), "USD", "yes"])
    csv = ["id,employee,date,category,amount,currency,receipt"] + [",".join(str(x) for x in r) for r in rows]
    policy = [
        "Travel and expense policy (excerpt)",
        "1. Alcohol is never reimbursed.",
        "2. Meals are reimbursed up to 40.00 USD per item; anything above is cut to 40.00.",
    ]
    if level >= 2:
        policy += [
            "3. Convert non-USD amounts to USD with rates.txt before applying any cap.",
            "4. Items without a receipt are reimbursed only if they are 25.00 USD or less after conversion; otherwise 0.",
        ]
    if level == 3:
        policy = policy[:2] + [
            "2. Meals: the total reimbursed for one employee on one date is capped at 60.00 USD (no per-item cap).",
        ] + policy[3:] + [
            "5. Duplicate claims (same employee, date, category and amount) are paid once.",
            "6. The receipt rule (4) is applied per item before the daily meal cap (2).",
        ]
    files = {"expenses.csv": "\n".join(csv) + "\n", "policy.md": "\n".join(policy) + "\n"}
    if level >= 2:
        files["rates.txt"] = "USD value of 1 unit\n" + "\n".join(f"{c} {v}" for c, v in RATES.items()) + "\n"

    def usd(r):
        return r[4] * RATES[r[5]]

    mine = [r for r in rows if r[1] == who and r[2].startswith(month) and r[3] != "alcohol"]
    total = 0.0
    if level < 3:
        for r in mine:
            v = usd(r)
            if level == 2 and r[6] == "no" and v > 25:
                continue
            if r[3] == "meal":
                v = min(v, 40.0)
            total += v
    else:
        seen = set()
        meals = {}
        for r in sorted(mine, key=lambda r: r[0]):
            key = (r[1], r[2], r[3], r[4], r[5])
            if key in seen:
                continue
            seen.add(key)
            v = usd(r)
            if r[6] == "no" and v > 25:
                continue
            if r[3] == "meal":
                meals[r[2]] = meals.get(r[2], 0.0) + v
            else:
                total += v
        total += sum(min(v, 60.0) for v in meals.values())
    target = round(total, 2)
    naive = round(sum(usd(r) for r in rows if r[1] == who), 2)
    return Built(
        question=(
            f"Using expenses.csv and policy.md, how much should {who} be reimbursed in USD for {month}? "
            "Round to cents."
        ),
        files=files,
        check=lambda a: close(a, target, abs_tol=0.02),
        answer=target,
        answer_hint="a number such as 812.40",
        budget={1: 8, 2: 10, 3: 12}[level],
        wrong=[naive],
    )
