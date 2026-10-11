"""Independent solvers that read only the task files, to check labels are derivable."""
import random, re, sys, math
from datetime import datetime, timedelta
sys.path.insert(0, '.')
from shiftdesk.families import sec, ind, off, med, sci

def solve_sec(files, level):
    ev = []
    for line in files['auth.log'].splitlines():
        m = re.search(r'(\w{3}\s+\d+ \d\d:\d\d:\d\d) .*sshd\[\d+\]: (Failed|Accepted) password for (?:invalid user )?(\S+) from (\S+)', line)
        if m:
            t = datetime.strptime('2026 ' + re.sub(r'\s+', ' ', m.group(1)), '%Y %b %d %H:%M:%S')
            ev.append((t, m.group(2) == 'Accepted', m.group(3), m.group(4)))
    if level == 1:
        from collections import Counter
        c = Counter(ip for t, ok, u, ip in ev if not ok)
        top = c.most_common(2)
        assert top[0][1] > top[1][1]
        return top[0][0]
    key = (lambda ip: ip) if level == 2 else (lambda ip: '.'.join(ip.split('.')[:3]) + '.0/24')
    hits = set()
    groups = {}
    for t, ok, u, ip in ev:
        groups.setdefault((key(ip), u), []).append((t, ok))
    for (src, u), lst in groups.items():
        fails = [t for t, ok in lst if not ok]
        succ = [t for t, ok in lst if ok]
        for i in range(len(fails)):
            j = i + 4
            if j < len(fails) and fails[j] - fails[i] <= timedelta(minutes=10):
                last = fails[j]
                # last failure of the burst = last failure before success
                for s in succ:
                    prior = [f for f in fails if f <= s]
                    if prior and s - prior[-1] <= timedelta(minutes=10) and len([f for f in prior if prior[-1]-f <= timedelta(minutes=10)]) >= 5:
                        hits.add(src)
    assert len(hits) == 1, hits
    return hits.pop()

bad = 0
for lvl in (1, 2, 3):
    for s in range(300):
        b = sec.build(lvl, random.Random(s))
        try:
            got = solve_sec(b.files, lvl)
            if b.check(got) != 1: bad += 1; print('sec mismatch', lvl, s, got, b.answer)
        except AssertionError as e:
            bad += 1; print('sec ambiguous', lvl, s, e)
print('sec bad', bad)

def tl(files):
    rows = [l.split(',') for l in files['states.csv'].splitlines()[1:]]
    per = {}
    for t, m, st in rows:
        h, mi = map(int, t.split(':')); per.setdefault(m, []).append((h*60+mi-360, st))
    out = {}
    for m, lst in per.items():
        lst.append((480, None)); run = brk = 0
        for (a, s1), (b2, _) in zip(lst, lst[1:]):
            if s1 == 'RUN': run += b2-a
            if s1 == 'BREAK': brk += b2-a
        out[m] = (run, 480-brk)
    return out
bad = 0
for lvl in (1, 2, 3):
    for s in range(200):
        b = ind.build(lvl, random.Random(s)); st = tl(b.files)
        if lvl == 1:
            m = re.search(r'machine (M\d+)', b.question).group(1); got = round(100*st[m][0]/480, 1)
        else:
            prod = {r.split(',')[0]: list(map(int, r.split(',')[1:])) for r in b.files['production.csv'].splitlines()[1:]}
            oee = {m: 100*prod[m][0]*prod[m][2]/(st[m][1]*60) for m in prod}
            for m in prod: assert prod[m][0]*prod[m][1] <= st[m][0]*60 + 1e-9, 'perf>1'
            if lvl == 2:
                m = re.search(r'machine (M\d+)', b.question).group(1); got = round(oee[m], 1)
            else:
                w = min(oee, key=oee.get); got = f'{w} {oee[w]:.1f}'
        if b.check(got) != 1: bad += 1; print('ind', lvl, s, got, b.answer)
print('ind bad', bad)

bad = 0
for lvl in (1, 2, 3):
    for s in range(200):
        b = med.build(lvl, random.Random(s))
        if lvl != 3: continue
        cues = re.findall(r'(\d+)\n(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})\n\w+: (.*)\n', b.files['episode.srt'] + '\n')
        badset = set()
        prev_end = -1
        for c in cues:
            n = int(c[0]); st = ((int(c[1])*60+int(c[2]))*60+int(c[3]))*1000+int(c[4]); en = ((int(c[5])*60+int(c[6]))*60+int(c[7]))*1000+int(c[8])
            assert st >= prev_end; prev_end = en
            if len(c[9].replace(' ', '')) / ((en-st)/1000) > 17: badset.add(n)
        if b.check(','.join(map(str, sorted(badset)))) != 1: bad += 1; print('med', s)
print('med bad', bad)
