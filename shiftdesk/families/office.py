"""Office and white-collar v3 families: meeting scheduling and three-way invoice matching."""
from ..grading import close, fields, same_list, same_text
from .base import Built

DOMAIN = "office-white-collar"

STAFF = [("Ama", "Accra", 0), ("Ben", "London", 1), ("Chen", "Singapore", 8), ("Dev", "Mumbai", 5.5),
         ("Eva", "Berlin", 2), ("Femi", "Lagos", 1), ("Gia", "New York", -4), ("Hugo", "Sao Paulo", -3)]


def _hm(m):
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"


class MeetingSlot:
    NAME = "meeting-slot"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        people = rng.sample(STAFF, 3 if level == 1 else 4)
        if max(p[2] for p in people) - min(p[2] for p in people) > 8:
            return MeetingSlot.build(level, rng)
        dur = rng.choice([30, 45, 60])
        busy = {}  # local minutes
        for name, city, off in people:
            blocks = []
            for _ in range(rng.randint(2, 4)):
                s = rng.randrange(9 * 60, 16 * 60, 15)
                blocks.append((s, s + rng.choice([30, 45, 60, 90])))
            busy[name] = sorted(blocks)
        moved = None
        if level == 2:
            name = people[rng.randrange(len(people))][0]
            old = rng.choice(busy[name])
            s = rng.randrange(9 * 60, 16 * 60, 15)
            new = (s, s + old[1] - old[0])
            moved = (name, old, new)

        def final_busy(apply_move):
            out = {k: list(v) for k, v in busy.items()}
            if apply_move and moved:
                out[moved[0]].remove(moved[1])
                out[moved[0]].append(moved[2])
            return out

        def earliest(bz):
            for t in range(0, 24 * 60 - dur + 1, 15):  # t in UTC minutes
                ok = True
                for name, city, off in people:
                    ls = t + off * 60
                    le = ls + dur
                    if ls < 9 * 60 or le > 17 * 60:
                        ok = False
                        break
                    if any(ls < b[1] and b[0] < le for b in bz[name]):
                        ok = False
                        break
                if ok:
                    return t
            return None

        ans = earliest(final_busy(True))
        naive = earliest(final_busy(False))
        if ans is None or (level == 2 and naive == ans):
            return MeetingSlot.build(level, rng)
        cal = ["person,city,utc_offset_hours,busy_local"]
        for name, city, off in people:
            cal.append(f"{name},{city},{off:+g}," + ";".join(f"{_hm(a)}-{_hm(b)}" for a, b in busy[name]))
        files = {"calendars.csv": "\n".join(cal) + "\n",
                 "request.txt": (f"Please book a {dur}-minute call with everyone in calendars.csv on the same day.\n"
                                 "Everyone works 09:00-17:00 local time; the call must fit fully inside every "
                                 "person's working hours and avoid every busy block. Start times are on the quarter hour.\n")}
        if level == 2:
            n, o, nw = moved
            files["inbox.txt"] = (f"From: {n}\nSubject: calendar change\n\nMy {_hm(o[0])}-{_hm(o[1])} (local) meeting "
                                  f"moved to {_hm(nw[0])}-{_hm(nw[1])} local. calendars.csv is out of date.\n")
        return Built(
            question="Find the earliest start time for the call, in UTC (HH:MM).",
            files=files,
            check=lambda a: fields(a, {"start_utc": lambda v: same_text(v, _hm(ans))}),
            answer={"start_utc": _hm(ans)},
            answer_hint='a JSON object {"start_utc": "13:15"}',
            budget=8,
            wrong=[{"start_utc": _hm(naive)}] if naive is not None and naive != ans else [{"start_utc": _hm(ans + 15)}],
        )


class InvoiceMatch:
    NAME = "invoice-match"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        vendors = rng.sample(["Kente Supplies", "Northwind", "Bluebird Ltd", "Oduro & Sons", "Apex Parts", "Lumen Co"], 4)
        pos, receipts, invoices = [], [], []
        for i in range(rng.randint(7, 10)):
            po = f"PO-{rng.randint(4000, 4999)}"
            v = rng.choice(vendors)
            qty = rng.randint(5, 120)
            price = round(rng.uniform(2, 80), 2)
            pos.append((po, v, qty, price))
            rq = qty if rng.random() < 0.75 else qty - rng.randint(1, min(4, qty - 1))
            receipts.append((po, rq))
            iq = qty if rng.random() < 0.8 else rq
            ip = price if rng.random() < 0.75 else round(price * rng.choice([1.01, 1.04, 1.1]), 2)
            iv = v if rng.random() < 0.88 else rng.choice([x for x in vendors if x != v])
            invoices.append((f"INV-{rng.randint(10000, 99999)}", po, iv, iq, ip))
        tol = 0.02
        credits = []
        if level == 2:
            for inv in rng.sample(invoices, 2):
                credits.append((f"CN-{rng.randint(100, 999)}", inv[0], round(inv[3] * inv[4] * rng.choice([0.05, 0.1]), 2)))
        po_map = {p[0]: p for p in pos}
        rc = dict(receipts)
        cn = {c[1]: c[2] for c in credits}
        approved, total = [], 0.0
        naive_ids = []
        for inv_id, po, v, iq, ip in invoices:
            p = po_map[po]
            price_ok = ip <= p[3] * (1 + tol) + 1e-9
            if iq <= rc[po] and price_ok and v == p[1]:
                approved.append(inv_id)
                total += iq * ip - cn.get(inv_id, 0.0)
            if iq <= p[2] and price_ok:
                naive_ids.append(inv_id)
        if not approved or len(approved) == len(invoices) or sorted(naive_ids) == sorted(approved):
            return InvoiceMatch.build(level, rng)
        files = {
            "purchase_orders.csv": "po,vendor,qty,unit_price\n" + "".join(f"{a},{b},{c},{d}\n" for a, b, c, d in pos),
            "receipts.csv": "po,qty_received\n" + "".join(f"{a},{b}\n" for a, b in receipts),
            "invoices.csv": "invoice,po,vendor,qty,unit_price\n" + "".join(f"{a},{b},{c},{d},{e}\n" for a, b, c, d, e in invoices),
            "ap_policy.txt": ("Accounts payable: three-way match\n"
                              "Approve an invoice only if: its vendor matches the PO vendor; invoiced qty <= qty received "
                              "(receipts.csv, not the PO qty); invoiced unit price <= PO unit price x 1.02.\n"
                              "Amount payable for an approved invoice = qty x unit price"
                              + (", minus any credit note issued against it (credit_notes.csv)." if level == 2 else ".")
                              + "\n"),
        }
        if level == 2:
            files["credit_notes.csv"] = "credit_note,invoice,amount\n" + "".join(f"{a},{b},{c}\n" for a, b, c in credits)
        return Built(
            question="Which invoices can be approved under ap_policy.txt, and what is the total payable for them?",
            files=files,
            check=lambda a: fields(a, {"approved": lambda v: same_list(v, approved, case=True),
                                       "total": lambda v: close(v, total, abs_tol=0.01)}),
            answer={"approved": sorted(approved), "total": round(total, 2)},
            answer_hint='a JSON object {"approved": ["INV-12345"], "total": 1234.56}',
            budget=8,
            wrong=[{"approved": sorted(naive_ids), "total": round(total, 2)}],
        )
