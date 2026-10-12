"""Every task: reference answer scores 1 (as object and as JSON string), wrong answers and empty answers score 0,
instances are deterministic per seed, and generation is fast."""
import json, random, sys, time
sys.path.insert(0, '.')
from shiftdesk.families import parse_task_id, task_ids

N = int(sys.argv[1]) if len(sys.argv) > 1 else 150
bad = 0
for tid in task_ids():
    fam, lvl = parse_task_id(tid)
    t0 = time.time(); same_wrong = 0; ans_lens = []
    for s in range(N):
        b = fam.build(lvl, random.Random(s))
        b2 = fam.build(lvl, random.Random(s))
        if b2.files != b.files or b2.question != b.question:
            bad += 1; print('nondeterministic', tid, s)
        if b.check(b.answer) != 1.0:
            bad += 1; print('ref fails', tid, s, b.answer); continue
        if isinstance(b.answer, (dict, list)) and b.check(json.dumps(b.answer)) != 1.0:
            bad += 1; print('ref-as-json fails', tid, s)
        for w in b.wrong:
            if w == b.answer:
                same_wrong += 1; continue
            if b.check(w) != 0.0:
                bad += 1; print('wrong scores', tid, s, w, b.answer)
        for e in ("", {}, [], None, "none", 0):
            if b.check(e) != 0.0:
                bad += 1; print('empty scores', tid, s, repr(e))
        size = sum(len(c) for c in b.files.values())
        ans_lens.append(size)
    dt = (time.time() - t0) / N
    print(f"{tid:24s} ok  {dt*1000:6.1f} ms/build  files~{sum(ans_lens)//len(ans_lens)} chars  wrong==ref:{same_wrong}")
print('FAMILY BAD', bad)
sys.exit(1 if bad else 0)
