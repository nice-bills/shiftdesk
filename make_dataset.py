"""Write dataset/tasks.jsonl: one row per task with a seed-0 example question and file names. No answers."""
import json, random, sys
sys.path.insert(0, '.')
from shiftdesk.families import parse_task_id, task_ids

with open('dataset/tasks.jsonl', 'w') as out:
    for tid in task_ids():
        fam, lvl = parse_task_id(tid)
        b = fam.build(lvl, random.Random(0))
        out.write(json.dumps({
            "task_id": tid, "domain": fam.DOMAIN, "family": fam.NAME, "level": lvl, "budget_calls": b.budget,
            "example_question": b.question, "answer_format": b.answer_hint, "files": sorted(b.files),
        }) + "\n")
print(len(task_ids()), "tasks written")
