"""Independent solvers for the v3 families. Each reads only what the agent sees (question + files),
written separately from the generators, and must earn reward 1 on every seed. This checks that every
label is derivable from the visible data and that the grader is honest."""
import csv, io, itertools, json, math, random, re, sys
from fractions import Fraction
sys.path.insert(0, '.')
from shiftdesk.families import parse_task_id

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def hm(s):
    h, m = s.split(':')
    return int(h) * 60 + int(m)


def s_beer(q, f, lvl):
    notes = f['notebook.txt']
    blank = float(re.search(r'blank \(([\d.]+) AU\)', notes).group(1)) if 'blank' in notes else 0.0
    bad = re.search(r'standard (S\d+) was mis-pipetted', notes)
    st = [r for r in rows(f['standards.csv']) if not (bad and r['standard'] == bad.group(1))]
    xs = [float(r['conc_uM']) for r in st]; ys = [float(r['absorbance']) - blank for r in st]
    n = len(xs); sx, sy = sum(xs), sum(ys); sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
    m = (n * sxy - sx * sy) / (n * sxx - sx * sx); b = (sy - m * sx) / n
    sid = re.search(r'sample (U\d+)', q).group(1)
    smp = next(r for r in rows(f['samples.csv']) if r['sample'] == sid)
    return {"slope": m, "concentration_uM": (float(smp['absorbance']) - blank - b) / m * float(smp['dilution_factor'])}


def s_stoich(q, f, lvl):
    masses = {l.split()[0]: float(l.split()[1]) for l in f['atomic_masses.txt'].splitlines()[1:] if l.strip()}
    mm = lambda fo: sum(masses[e] * (int(k) if k else 1) for e, k in re.findall(r'([A-Z][a-z]?)(\d*)', fo))
    b = f['batch.txt']
    lhs, rhs = re.search(r'Reaction: (.*) -> (.*)', b).groups()
    def terms(side):
        out = []
        for t in side.split(' + '):
            p = t.split()
            out.append((int(p[0]), p[1]) if len(p) == 2 else (1, p[0]))
        return out
    (a, A), (bb, B) = terms(lhs)
    c, P = terms(rhs)[0]
    ma = float(re.search(r'([\d.]+) g of ' + re.escape(A), b).group(1))
    mb = float(re.search(r'([\d.]+) g of ' + re.escape(B) + r'\.', b).group(1))
    pa = pb = eff = 100.0
    if 'purity' in b:
        pa = float(re.search(re.escape(A) + r' ([\d.]+)%', b).group(1))
        pb = float(re.search(re.escape(B) + r' ([\d.]+)%', b).group(1))
        eff = float(re.search(r'yield for this process: ([\d.]+)%', b).group(1))
    xa = ma * pa / 100 / mm(A) / a; xb = mb * pb / 100 / mm(B) / bb
    lim = A if xa < xb else B
    g = min(xa, xb) * c * mm(P) * eff / 100
    return {"limiting": lim, ("expected_g" if lvl == 2 else "theoretical_g"): g}


def npv(r, fl):
    return sum(v / (1 + r) ** t for t, v in enumerate(fl))


def s_npv(q, f, lvl):
    memo = f['memo.txt']
    data = {r['project']: (r['risk_class'], [float(r[k]) for k in r if k.startswith('y')]) for r in rows(f['projects.csv'])}
    m = re.search(r'(P\d+) y(\d+) should read (\d+)', memo)
    if m:
        data[m.group(1)][1][int(m.group(2))] = float(m.group(3))
    if 'risk class' in memo:
        rates = {k: float(v) / 100 for k, v in re.findall(r'(low|medium|high) ([\d.]+)%', memo)}
        vals = {p: npv(rates[rc], fl) for p, (rc, fl) in data.items()}
    else:
        r = float(re.search(r'at ([\d.]+)% per year', memo).group(1)) / 100
        vals = {p: npv(r, fl) for p, (rc, fl) in data.items()}
    best = max(vals, key=vals.get)
    return {"best_project": best, "npv": vals[best]}


def s_bond(q, f, lvl):
    bid = re.search(r'bond (BD\d+)', q).group(1)
    r = next(x for x in rows(f['bonds.csv']) if x['bond_id'] == bid)
    face, cp, fr, yrs, y = float(r['face']), float(r['coupon_pct']), int(r['coupons_per_year']), int(r['years_to_maturity']), float(r['ytm_pct'])
    i = y / 100 / fr; n = yrs * fr; cpn = face * cp / 100 / fr
    pv = [(k, (cpn + (face if k == n else 0)) / (1 + i) ** k) for k in range(1, n + 1)]
    price = sum(v for _, v in pv)
    out = {"price": price}
    if lvl == 2:
        out["modified_duration"] = sum(k / fr * v for k, v in pv) / price / (1 + i)
    return out


def s_fifo(q, f, lvl):
    tick = re.search(r'For (\w+) only', q).group(1)
    lots, gain = [], 0.0
    for r in rows(f['trades.csv']):
        if r['ticker'] != tick:
            continue
        if r['action'] == 'SPLIT':
            k = int(r['quantity']); lots = [[a * k, c / k] for a, c in lots]; continue
        qty, px, fee = int(r['quantity']), float(r['price']), float(r['fee'] or 0)
        if r['action'] == 'BUY':
            lots.append([qty, (qty * px + fee) / qty])
        else:
            cost, left = 0.0, qty
            while left:
                t = min(left, lots[0][0]); cost += t * lots[0][1]; lots[0][0] -= t; left -= t
                if not lots[0][0]:
                    lots.pop(0)
            gain += qty * px - fee - cost
    return {"realized_gain": gain, "shares_held": sum(a for a, _ in lots)}


def s_crt(q, f, lvl):
    txt = f['system.txt']
    cs = [(int(a), int(m)) for a, m in re.findall(r'x = (\d+) \(mod (\d+)\)', txt)]
    x, M = 0, 1
    for a, m in cs:
        while x % m != a:
            x += M
        M = M * m // math.gcd(M, m)
    out = {"x": x, "modulus": M}
    r = re.search(r'with (\d+) <= x <= (\d+)', txt)
    if r:
        lo, hi = int(r.group(1)), int(r.group(2))
        out["count_in_range"] = sum(1 for v in range(lo, hi + 1) if v % M == x)
    return out


def s_logic(q, f, lvl):
    t = f['puzzle.txt']
    order = re.search(r'left to right: (.*)\.', t).group(1).split(', ')
    opts = {k: v.split(', ') for k, v in re.findall(r'(\w+): ([\w, ]+?)(?:;|\.$)', t.splitlines()[2].replace('Options: ', ''))}
    attrs = list(opts)
    clues = t.split('Clues:')[1].strip().splitlines()
    sols = []
    for combo in itertools.product(*[itertools.permutations(opts[a]) for a in attrs]):
        s = {a: dict(zip(order, combo[i])) for i, a in enumerate(attrs)}
        who = lambda a, v: next(p for p in order if s[a][p] == v)
        ok = True
        for c in clues:
            c = c.split('. ', 1)[1]
            m = re.match(r"(\w+)'s (\w+) is (not )?(\w+)\.", c)
            if m:
                eq = s[m.group(2)][m.group(1)] == m.group(4)
                ok = eq != bool(m.group(3))
            elif ' sits directly left of ' in c:
                m = re.match(r'The person whose (\w+) is (\w+) sits directly left of the person whose (\w+) is (\w+)\.', c)
                ok = order.index(who(m.group(1), m.group(2))) + 1 == order.index(who(m.group(3), m.group(4)))
            else:
                m = re.match(r'The person whose (\w+) is (\w+) has (\w+) (\w+)\.', c)
                ok = s[m.group(3)][who(m.group(1), m.group(2))] == m.group(4)
            if not ok:
                break
        if ok:
            sols.append(s)
    assert len(sols) == 1, len(sols)
    at = re.search(r"each person's (\w+)", q).group(1)
    return sols[0][at]


def s_route(q, f, lvl):
    closed = set()
    if 'notice.txt' in f:
        for a, b in re.findall(r'(\w)-(\w)', f['notice.txt'].split(':', 1)[1]):
            closed.add(frozenset((a, b)))
    g = {}
    for r in rows(f['roads.csv']):
        if frozenset((r['from'], r['to'])) in closed:
            continue
        g.setdefault(r['from'], []).append((r['to'], int(r['minutes'])))
        g.setdefault(r['to'], []).append((r['from'], int(r['minutes'])))
    src, dst = re.search(r'from (\w) to (\w)', q).groups()
    via = re.search(r'passes through (\w)', q)
    def best(s, t):  # brute force over simple paths
        out = []
        def dfs(u, seen, cost):
            if u == t:
                out.append((cost, list(seen))); return
            for v, w in g.get(u, []):
                if v not in seen:
                    seen.append(v); dfs(v, seen, cost + w); seen.pop()
        dfs(s, [s], 0)
        return out
    if via:
        v = via.group(1)
        c1 = min(best(src, v)); c2 = min(best(v, dst))
        return {"minutes": c1[0] + c2[0], "route": c1[1] + c2[1][1:]}
    c = min(best(src, dst))
    return {"minutes": c[0], "route": c[1]}


def s_prob(q, f, lvl):
    t = f['problem.txt']
    m = re.search(r'Roll (\d+) fair (\d+)-sided dice.*exactly (\d+)\?', t)
    if m:
        k, sd, s = map(int, m.groups())
        ways = [1]
        for _ in range(k):
            nw = [0] * (len(ways) + sd)
            for i, w in enumerate(ways):
                for d in range(1, sd + 1):
                    nw[i + d] += w
            ways = nw
        p = Fraction(ways[s], sd ** k)
    else:
        bag = [(int(n), c) for n, c in re.findall(r'(\d+) (\w+)', t.split(' marbles.')[0])]
        d = int(re.search(r'Draw (\d+)', t).group(1)); need, col = re.search(r'at least (\d+) (\w+)', t).groups()
        need = int(need); k = next(n for n, c in bag if c == col); N = sum(n for n, _ in bag)
        p = Fraction(sum(math.comb(k, j) * math.comb(N - k, d - j) for j in range(need, d + 1)), math.comb(N, d))
    return {"probability": f"{p.numerator}/{p.denominator}"}


def s_fw(q, f, lvl):
    import ipaddress
    rl = [l for l in f['rules.txt'].splitlines() if l and not l.startswith('#')]
    if 'change_log.txt' in f:
        c = f['change_log.txt']
        m = re.search(r'rule (R\d+) was deleted', c)
        if m:
            rl = [l for l in rl if not l.startswith(m.group(1) + ' ')]
        m = re.search(r'inserted at the top of the live firewall: (\w+) (\w+) from (\S+) to port (\S+)\.', c)
        if m:
            rl = [f"R0 {m.group(1)} proto={m.group(2)} src={m.group(3)} dport={m.group(4)}"] + rl
    parsed = []
    for l in rl:
        p = l.split()
        kv = dict(x.split('=') for x in p[2:])
        lo, _, hi = kv['dport'].partition('-')
        parsed.append((p[1], kv['proto'], ipaddress.ip_network(kv['src']), int(lo), int(hi or lo)))
    allowed = []
    for r in rows(f['packets.csv']):
        ip = ipaddress.ip_address(r['src_ip']); port = int(r['dst_port'])
        verdict = 'deny'
        for act, pr, net, lo, hi in parsed:
            if (pr == 'any' or pr == r['proto']) and ip in net and lo <= port <= hi:
                verdict = act; break
        if verdict == 'allow':
            allowed.append(r['id'])
    return {"allowed": allowed}


def s_vuln(q, f, lvl):
    v = lambda s: tuple(map(int, s.split('.')))
    adv = json.loads(f['advisories.json'])
    bp = set(re.findall(r'- (\S+): (\S+) \(', f.get('vendor_notes.txt', '')))
    hosts = set()
    for r in rows(f['inventory.csv']):
        for a in adv:
            if a['package'] != r['package'] or (r['host'], r['package']) in bp:
                continue
            lo, hi = re.match(r'>=(\S+), <(\S+)', a['affected_versions']).groups()
            if v(lo) <= v(r['version']) < v(hi):
                hosts.add(r['host'])
    return {"hosts": sorted(hosts), "count": len(hosts)}


def s_edl(q, f, lvl):
    t = f['timeline.edl']
    fps = int(re.search(r'FPS: (\d+)', t).group(1))
    fr = lambda tc: (lambda h, m, s, x: ((h * 60 + m) * 60 + s) * fps + x)(*map(int, tc.split(':')))
    clips = {r['clip']: [fr(r['source_in']), fr(r['source_out'])] for r in csv.DictReader(io.StringIO(t.split('\n', 2)[2]))}
    extra = 0
    if 'review_notes.txt' in f:
        n = f['review_notes.txt']
        clips.pop(re.search(r'drop (C\d+)', n).group(1))
        m = re.search(r'Trim (\d+) frames off the end of (C\d+)', n); clips[m.group(2)][1] -= int(m.group(1))
        extra = int(re.search(r'a (\d+)-frame black slug', n).group(1))
    tot = sum(b - a for a, b in clips.values()) + extra
    s = tot // fps
    return {"frames": tot, "timecode": f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{tot % fps:02d}"}


def s_head(q, f, lvl):
    g = f['style_guide_p1.txt']
    mx = int(re.search(r'At most (\d+) characters', g).group(1))
    banned = [w.strip() for w in re.search(r'these words: (.*)\.', g).group(1).split(',')]
    brands = []
    if 'style_guide_p2.txt' in f:
        brands = [w.strip() for w in f['style_guide_p2.txt'].split('headline:')[1].strip().rstrip('.').split(',')]
    out = []
    for line in f['headlines.tsv'].splitlines()[1:]:
        hid, h = line.split('\t')
        ws = h.rstrip('.').split()
        badw = any(re.sub(r'\W', '', w).lower() in banned for w in ws)
        caps = any(w[0].isupper() and w not in brands for w in ws[1:]) or not ws[0][0].isupper()
        if len(h) > mx or h.endswith('.') or badw or caps:
            out.append(hid)
    return {"violations": out}


def s_bom(q, f, lvl):
    import math as m
    bom = rows(f['bom.csv'])
    top, units = re.search(r'build (\d+) x (\S+)\.', f['work_order.txt']).groups()[::-1]
    stock = {r['part']: int(r['on_hand']) for r in rows(f['stock.csv'])} if 'stock.csv' in f else {}
    parents = {r['parent'] for r in bom}
    need = {}
    def go(part, qty):
        if part in stock:
            t = min(stock[part], qty); stock[part] -= t; qty -= t
        if qty <= 0:
            return
        kids = [r for r in bom if r['parent'] == part]
        if not kids:
            need[part] = need.get(part, 0) + qty; return
        for r in kids:
            sc = float(r.get('scrap_pct') or 0)
            go(r['child'], m.ceil(int(r['qty_per_parent']) * qty * (1 + sc / 100) - 1e-9))
    for r in [r for r in bom if r['parent'] == top]:
        sc = float(r.get('scrap_pct') or 0)
        go(r['child'], m.ceil(int(r['qty_per_parent']) * int(units) * (1 + sc / 100) - 1e-9))
    return need


def s_tank(q, f, lvl):
    t = f['tank.txt']
    cap = int(re.search(r'capacity (\d+) L', t).group(1)); lv = float(re.search(r'was (\d+) L', t).group(1))
    alarm = int(re.search(r'alarm at (\d+) L', t).group(1))
    off = None
    if 'shift_log.txt' in f:
        off = re.search(r'from (\d\d:\d\d) to', f['shift_log.txt']).group(1)
    first = None
    for r in rows(f['flows.csv']):
        a, b = hm(r['start']), hm(r['end'])
        rate = int(r['inflow_l_per_min']) - (0 if r['start'] == off else int(r['outflow_l_per_min']))
        for minute in range(a, b):  # minute-by-minute simulation
            nxt = lv + rate
            if first is None and lv < alarm <= nxt:
                first = minute + math.ceil((alarm - lv) / rate - 1e-9) if rate else None
            lv = nxt
            if lvl == 2:
                lv = min(cap, max(0.0, lv))
    return {"final_level_l": lv, "first_alarm": f"{first // 60:02d}:{first % 60:02d}"}


def s_meet(q, f, lvl):
    dur = int(re.search(r'book a (\d+)-minute', f['request.txt']).group(1))
    cal = {}
    for r in rows(f['calendars.csv']):
        cal[r['person']] = (float(r['utc_offset_hours']), [tuple(map(hm, b.split('-'))) for b in r['busy_local'].split(';')])
    if 'inbox.txt' in f:
        m = re.search(r'From: (\w+).*My (\d\d:\d\d)-(\d\d:\d\d) \(local\) meeting moved to (\d\d:\d\d)-(\d\d:\d\d)', f['inbox.txt'], re.S)
        p = m.group(1); old = (hm(m.group(2)), hm(m.group(3))); new = (hm(m.group(4)), hm(m.group(5)))
        bl = cal[p][1]; bl.remove(old); bl.append(new)
    for t in range(0, 1440, 15):
        if all(540 <= t + o * 60 and t + o * 60 + dur <= 1020 and
               not any(t + o * 60 < e and s < t + o * 60 + dur for s, e in bl) for o, bl in cal.values()):
            return {"start_utc": f"{t // 60:02d}:{t % 60:02d}"}


def s_inv(q, f, lvl):
    po = {r['po']: r for r in rows(f['purchase_orders.csv'])}
    rc = {r['po']: int(r['qty_received']) for r in rows(f['receipts.csv'])}
    cn = {}
    for r in rows(f.get('credit_notes.csv', 'credit_note,invoice,amount\n')):
        cn[r['invoice']] = cn.get(r['invoice'], 0) + float(r['amount'])
    ok, tot = [], 0.0
    for r in rows(f['invoices.csv']):
        p = po[r['po']]
        if r['vendor'] == p['vendor'] and int(r['qty']) <= rc[r['po']] and float(r['unit_price']) <= float(p['unit_price']) * 1.02 + 1e-9:
            ok.append(r['invoice']); tot += int(r['qty']) * float(r['unit_price']) - cn.get(r['invoice'], 0)
    return {"approved": ok, "total": tot}


def s_impact(q, f, lvl):
    g = json.loads(f['modules.json'])
    deps = {m: (v['deps'] if isinstance(v, dict) else v) for m, v in g.items()}
    ch = f['change.txt'].split(':')[1].strip().split(', ')
    aff = set(ch)
    while True:
        more = {m for m, d in deps.items() if set(d) & aff} - aff
        if not more:
            break
        aff |= more
    order, left = [], set(aff)
    while left:
        m = min(x for x in left if not (set(deps[x]) & left))
        order.append(m); left.remove(m)
    return {"rebuild": sorted(aff), "build_order": order}


def s_ver(q, f, lvl):
    reg = json.loads(f['registry.json'])
    v = lambda s: tuple(map(int, s.split('.')))
    yank = set(re.findall(r'(\w+)==(\S+?)(?:,|$|\s)', f.get('advisory.txt', '')))
    req = {}
    for line in f['requirements.txt'].splitlines():
        spec = line.split('#')[0].strip()
        p, s = spec.split(' ', 1)
        req.setdefault(p, []).append(s)
    def ok(ver, s):
        x = v(ver)
        for part in [t.strip() for t in s.split(',')]:
            if part[0] == '^':
                b = v(part[1:]); hi = (b[0] + 1, 0, 0) if b[0] else (0, b[1] + 1, 0)
                if not b <= x < hi: return False
            elif part[0] == '~':
                b = v(part[1:])
                if not b <= x < (b[0], b[1] + 1, 0): return False
            elif part.startswith('>='):
                if x < v(part[2:]): return False
            elif part[0] == '<':
                if not x < v(part[1:]): return False
        return True
    out = {}
    for p, specs in req.items():
        c = [x for x in reg[p] if all(ok(x, s) for s in specs) and (p, x) not in yank]
        out[p] = max(c, key=v) if c else "none"
    return out


SOLVERS = {
    'beer-lambert': s_beer, 'stoichiometry': s_stoich, 'npv-choice': s_npv, 'bond-desk': s_bond,
    'fifo-basis': s_fifo, 'congruences': s_crt, 'logic-grid': s_logic, 'shortest-route': s_route,
    'exact-probability': s_prob, 'firewall-audit': s_fw, 'vuln-triage': s_vuln, 'edit-timeline': s_edl,
    'headline-style': s_head, 'bom-explosion': s_bom, 'tank-balance': s_tank, 'meeting-slot': s_meet,
    'invoice-match': s_inv, 'change-impact': s_impact, 'version-resolve': s_ver,
}

bad = 0
for name, fn in SOLVERS.items():
    fam = parse_task_id(f"{name}-L1")[0]
    for lvl in fam.LEVELS:
        miss = 0
        for s in range(N):
            b = fam.build(lvl, random.Random(1000 + s))
            try:
                got = fn(b.question, b.files, lvl)
                r = b.check(got)
            except Exception as e:
                r = 0.0; got = f"error {type(e).__name__}: {e}"
            if r != 1.0:
                miss += 1
                if miss <= 2:
                    print('  MISMATCH', name, lvl, s, 'solver:', got, 'label:', b.answer)
        bad += miss
        print(f"{name}-L{lvl:<3d} independent solver agrees on {N - miss}/{N}")
print('SOLVER BAD', bad)
sys.exit(1 if bad else 0)
