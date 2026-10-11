"""Finance: loan schedules read from files with distractors."""
from ..grading import close
from .base import Built

DOMAIN = "finance-economics"
NAME = "loan-desk"


def _payment(principal, annual_rate, months):
    r = annual_rate / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def _balance_after(principal, annual_rate, months, k):
    r = annual_rate / 12
    pay = round(_payment(principal, annual_rate, months), 2)
    bal = principal
    for _ in range(k):
        interest = round(bal * r, 2)
        bal = round(bal + interest - pay, 2)
    return bal, pay


def _interest_with_extra(principal, annual_rate, months, extra):
    r = annual_rate / 12
    pay = round(_payment(principal, annual_rate, months), 2)
    bal = principal
    total_interest = 0.0
    count = 0
    while bal > 0.005 and count < 2000:
        interest = round(bal * r, 2)
        total_interest += interest
        due = pay + extra
        if bal + interest <= due:
            bal = 0.0
        else:
            bal = round(bal + interest - due, 2)
        count += 1
    return round(total_interest, 2), count


def _loans(rng, n):
    rows = []
    used = set()
    for _ in range(n):
        while True:
            lid = f"LN-{rng.randint(1000, 9999)}"
            if lid not in used:
                used.add(lid)
                break
        principal = rng.randrange(8000, 400000, 500)
        rate = rng.choice([3.25, 3.9, 4.5, 4.75, 5.1, 5.6, 6.25, 6.8, 7.4, 8.15, 9.0])
        years = rng.choice([3, 5, 7, 10, 15, 20, 30])
        rows.append((lid, principal, rate, years))
    return rows


def build(level, rng):
    if level == 1:
        principal = rng.randrange(5000, 90000, 250)
        rate = rng.choice([4.2, 5.5, 6.9, 7.25, 8.4, 11.9])
        years = rng.choice([2, 3, 4, 5, 6])
        note = (
            "Quote request\n"
            f"Customer wants to borrow ${principal:,} at {rate}% APR, compounded monthly,\n"
            f"repaid in equal monthly payments over {years} years. First payment one month after funding.\n"
        )
        pay = _payment(principal, rate / 100, years * 12)
        return Built(
            question="Read quote.txt. What is the fixed monthly payment in dollars? Round to cents.",
            files={"quote.txt": note},
            check=lambda a: close(a, pay, abs_tol=0.01),
            answer=round(pay, 2),
            answer_hint="a number such as 1234.56",
            budget=8,
            wrong=[round(principal * (1 + rate / 100 * years) / (years * 12), 2)],
        )
    rows = _loans(rng, 6 if level == 2 else 9)
    target = rng.choice(rows)
    lid, principal, rate, years = target
    lines = ["loan_id,principal_usd,apr_percent,term_years,status"]
    for row in rows:
        status = rng.choice(["active", "active", "active", "refinanced"]) if row != target else "active"
        lines.append(f"{row[0]},{row[1]},{row[2]},{row[3]},{status}")
    rules = (
        "Servicing rules\n"
        "- Interest accrues monthly at APR/12 on the outstanding balance.\n"
        "- The scheduled payment is the level annuity payment for the full term, rounded to cents.\n"
        "- Each month: interest = round(balance * APR/12, 2); balance = balance + interest - payment.\n"
    )
    if level == 2:
        k = rng.randint(6, min(years * 12 - 2, 90))
        bal, pay = _balance_after(principal, rate / 100, years * 12, k)
        return Built(
            question=(
                f"Use loans.csv and rules.txt. What is the outstanding balance of loan {lid} "
                f"right after its {k}th scheduled payment? Dollars, rounded to cents."
            ),
            files={"loans.csv": "\n".join(lines) + "\n", "rules.txt": rules},
            check=lambda a: close(a, bal, abs_tol=0.05),
            answer=bal,
            answer_hint="a number such as 98765.43",
            budget=10,
            wrong=[round(principal - k * pay, 2)],
        )
    extra = rng.choice([50, 75, 100, 150, 200, 250, 400])
    rules += (
        f"- The borrower of {lid} adds a fixed extra ${extra} to every payment from month 1.\n"
        "- The final payment is only what is needed to clear the balance (interest still accrues that month).\n"
    )
    total, months = _interest_with_extra(principal, rate / 100, years * 12, extra)
    plain = round(_payment(principal, rate / 100, years * 12) * years * 12 - principal, 2)
    return Built(
        question=(
            f"Use loans.csv and rules.txt. With the extra payments, how much total interest is paid on "
            f"loan {lid} until it is fully repaid? Dollars, rounded to cents."
        ),
        files={"loans.csv": "\n".join(lines) + "\n", "rules.txt": rules},
        check=lambda a: close(a, total, abs_tol=0.5),
        answer=total,
        answer_hint="a number such as 12345.67",
        budget=12,
        wrong=[plain],
    )
