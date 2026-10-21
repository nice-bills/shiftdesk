"""Write dataset/tasks.jsonl: one row per task with a seed-0 example question and file names. No answers."""
import json, random, sys
sys.path.insert(0, '.')
from shiftdesk.families import parse_task_id, task_ids, train_v4, v4_task_ids

SUBMITTED = set(train_v4())

with open('dataset/tasks.jsonl', 'w') as out:
    for tid in task_ids():
        fam, lvl = parse_task_id(tid)
        b = fam.build(lvl, random.Random(0))
        out.write(json.dumps({
            "task_id": tid, "domain": fam.DOMAIN, "family": fam.NAME, "level": lvl, "budget_calls": b.budget,
            "example_question": b.question, "answer_format": b.answer_hint, "files": sorted(b.files),
            "deliverable": b.deliverable or None, "style": "file" if b.deliverable else "answer",
            "new_in_v4": tid in v4_task_ids(), "in_training_list": tid in SUBMITTED,
        }) + "\n")
print(len(task_ids()), "tasks written")
