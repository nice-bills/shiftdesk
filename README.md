# ShiftDesk v3

An OpenEnv environment for OpenEnv Arena. 47 tasks from 27 procedural families covering all eight arena
domains (software 5, industrial 6, natural science 5, office 5, finance 7, math and formal reasoning 9,
cybersecurity 5, media 5). Every reset generates a fresh instance (files, question, answer) from a seeded
generator, so there are no fixed answer keys and this dataset holds none: `tasks.jsonl` lists each task id
with a seed-0 example question, the answer format and the file names.

## What the agent does

Each episode is a small workspace of text files and four plain tools, listed with one example call each in the
first observation:

- `list_files` `{}`
- `read_file` `{"path": ..., "offset": optional first line}` (2,500 characters per call)
- `run_python` `{"code": ...}` (Python 3 standard library, task files in the working directory, runs as `nobody`)
- `submit` `{"answer": ...}` ends the episode

Answers are small JSON objects with named fields (for example `{"best_project": "P41", "npv": 18234.55}`).

| Domain | Families (levels) |
|---|---|
| Software engineering | change-impact (1,2): rebuild set and deterministic build order with dev-only edges; version-resolve (1,2): semver ranges, plugin constraints, yanked releases; module-repair (3) |
| Industrial & physical | bom-explosion (1,2): BOM explosion with scrap and stock netting; tank-balance (1,2): level and alarm time with overflow and a tripped pump; line-oee (2,3) |
| Natural science | beer-lambert (1,2): least-squares calibration with blank subtraction, an excluded standard, dilution; stoichiometry (1,2): limiting reagent, purity, process yield; kinetics-lab (3) |
| Office & white-collar | meeting-slot (1,2): earliest common slot across time zones with a late calendar change; invoice-match (1,2): three-way match with tolerance and credit notes; expense-policy (3) |
| Finance & economics | npv-choice (1,2): NPV by risk class with errata; bond-desk (1,2): price and modified duration; fifo-basis (1,2): FIFO realized gain with fees and a split; loan-desk (3) |
| Math & formal reasoning | congruences (1,2): CRT with non-coprime moduli; logic-grid (1,2): unique-solution seating puzzles; shortest-route (1,2): closures and a waypoint; exact-probability (1,2): reduced fractions; exact-count (3) |
| Cybersecurity | firewall-audit (1,2): first-match rules with an approved change; vuln-triage (1,2): numeric semver ranges and vendor backports; auth-hunt (3) |
| Media & content | edit-timeline (1,2): EDL frames and timecode after review notes; headline-style (1,2): a two-page style guide; subtitle-qc (3) |

## What it is meant to teach

General desk habits rather than one tool's quirks: read every file (level-2 tasks put a correction, errata,
change log or second page in a separate file), compute with Python instead of by eye, and submit exactly the
requested JSON fields. Tool names are conventional and fixed; there is no ritual end action.

## Reward

All or nothing: 1.0 only when every requested field is right (numeric tolerances are stated in the answer
format; ids, lists, versions and timecodes match exactly, lists in any order unless an order is asked for),
otherwise 0.0. No answer, an empty answer, running out of calls, or an invalid reply scores 0.0. The finish
action `{"tool": "submit", "args": {"answer": ""}}` scores 0.0.

## Same instance for a group

Rollouts that reset the same task within the same 5-minute window get the same instance (seeded from a
secret in the image), so the parallel rollouts of an optimizer step are compared on one problem.

## Checks

For every task over 100+ seeds: the reference answer scores 1 as an object and as a JSON string, plausible
wrong answers (the answer you get by skipping the caveat file) and empty answers score 0, and generation is
deterministic per seed. For all 19 new families an independent solver that reads only the question and files
reproduces every label. `openenv validate` passes and every task replays to a terminal reward over WebSocket.

Source: https://github.com/nice-bills/shiftdesk

## Run the checks

```sh
pip install -r requirements.txt && pip install --no-deps vendor/openenv-0.6.1.dev0-py3-none-any.whl
python tests_families.py 100      # reference/wrong/empty answers, determinism
python tests_solvers_v3.py 100    # independent solvers agree with every label
python tests_solvers.py           # v1 family solvers
python tests_episodes.py          # in-process episodes over the four tools
uvicorn shiftdesk.server.app:app --port 8000 &
NO_PROXY=127.0.0.1 openenv validate --url http://127.0.0.1:8000
python tests_ws.py http://127.0.0.1:8000
python make_dataset.py            # rewrite dataset/tasks.jsonl
```
