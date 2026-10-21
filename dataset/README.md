---
license: apache-2.0
pretty_name: ShiftDesk
tags: [openenv, reinforcement-learning, agents, tool-use]
configs:
  - config_name: default
    data_files:
      - split: train
        path: tasks.jsonl
---
# ShiftDesk v4

An OpenEnv environment for OpenEnv Arena. v4 adds a terminal: a `bash` tool and a `write_file` tool next to
`list_files`, `read_file` and `run_python`, a working directory that persists for the whole episode, and 32 new
**file-deliverable** tasks (16 families x 2 levels) in the four domains where earlier versions never scored:
natural science, math and formal reasoning, cybersecurity, and media. Each asks for a real output file
(`output/results.csv`, `output/incident.json`, `output/out.srt`, `output/article.html`, ...) that hidden
checks grade on submit. All 47 v3 answer-style tasks are still served.

The training list (`in_training_list` in `tasks.jsonl`) has 53 tasks: the 32 new ones (60%) interleaved with
21 v3 tasks from software, industrial, office and finance (40%), so the domains that already score keep training.
Every reset generates a fresh instance from a seeded generator, so there are no fixed answer keys and this
dataset holds none: `tasks.jsonl` lists each task id with a seed-0 example question, its deliverable path or
answer format, and its file names.

## What the agent does

Each episode is a working directory with the task files and an empty `output/` folder. Tools, each shown with a
one-line JSON example in the first observation:

- `list_files` `{}`: everything in the working directory, including files the agent wrote
- `read_file` `{"path": ..., "offset": optional first line}` (2,500 characters per call)
- `write_file` `{"path": ..., "content": ...}`: create or overwrite a file inside the working directory
- `bash` `{"command": ...}`: a shell with python3, grep, awk, sed, sort, jq, sqlite3, bc, openssl, file
- `run_python` `{"code": ...}`: Python 3 with the standard library, numpy, sympy and PIL
- `submit` `{"answer": ...}` ends the episode (for file tasks the answer can be empty)

`bash` and `run_python` run as `nobody` with CPU, memory, file-size and process limits and a 20 s wall timeout;
`write_file` writes through the same sandboxed child. Outbound IPv4/IPv6 sockets are refused by a seccomp
filter. The instance salt and the server code are root-only.

| Domain | New v4 file families (levels 1, 2) |
|---|---|
| Natural science | assay-reduction: plate-reader calibration with mixed units, QC-flagged wells, replicates and out-of-range samples -> results.csv; peak-picking: spectrum peak table with baseline windows and cosmic-ray removal -> peaks.json; dilution-plan: direct and serial dilution plans from mg/mL stocks -> plan.csv; pk-fit: non-compartmental PK (AUC, k_el, half-life) with BLQ handling and clock-time sampling -> pk.json |
| Math & formal reasoning | linear-system: exact rational solutions with a redundant and a voided equation -> solution.json; recurrence-id: smallest linear recurrence (with constant) and a far term mod p -> answer.json; claim-check: exhaustive checks with smallest counterexamples -> verdicts.json; board-expectation: exact expected turns of a dice game with exact-landing and bonus rolls -> answer.json |
| Cybersecurity | web-forensics: nginx log attacker, UTC timeline and successful payloads in an unordered merged log -> incident.json; decode-chain: layered base64/hex/rot13/URL/XOR blobs and salted hash cracking -> decoded.json; sshd-audit: effective sshd_config (first value wins, defaults, Match blocks) against a baseline -> findings.json; jwt-inspect: HS256 verification with kid, exp/nbf, issuer, audience and a check order -> report.json |
| Media & content | srt-retime: offset and two-point linear retiming with credit removal and renumbering -> out.srt; image-audit: real format, EXIF-rotated display size and extension checks -> report.csv; audio-audit: WAV duration, peak dBFS and clipping -> audio_report.csv; markdown-html: Markdown to house-style HTML (slug ids, demoted h1s, external-link attributes) -> article.html |

v3 answer-style families (all still served): change-impact, version-resolve, module-repair (software);
bom-explosion, tank-balance, line-oee (industrial); beer-lambert, stoichiometry, kinetics-lab (science);
meeting-slot, invoice-match, expense-policy (office); npv-choice, bond-desk, fifo-basis, loan-desk (finance);
congruences, logic-grid, shortest-route, exact-probability, exact-count (math); firewall-audit, vuln-triage,
auth-hunt (security); edit-timeline, headline-style, subtitle-qc (media).

## What it is meant to teach

Terminal work the way held-out skills tasks are shaped: read every file (level 2 hides a caveat in a second file:
QC flags, an SOP step, errata, a sync sheet, a style guide), compute with code instead of by eye, and leave a
correctly formatted output file where the task asks for it.

## Reward

Binary. File tasks: 1.0 only when the deliverable exists at the requested path, is a regular file (symlinks are
refused), parses, and passes every hidden check (stated numeric tolerances; ids, lists, timestamps and HTML
structure exact); otherwise 0.0. The deliverable is graded on `submit`, on the finish action, and when calls run
out. Answer tasks (v3): 1.0 only when every requested JSON field is right. The finish action
`{"tool": "submit", "args": {"answer": ""}}` scores 0.0 unless the deliverable file is already correct.

## Same instance for a group

Rollouts that reset the same task within the same 5-minute window get the same instance (seeded from a
secret in the image), so the parallel rollouts of an optimizer step are compared on one problem.

## Checks

For every task over 60+ seeds: the reference scores 1, plausible wrong outputs (what you get by skipping the
caveat) and empty outputs score 0, and generation is deterministic per seed. For all 16 new families an
independent solver that reads only the question and files plays full episodes through `write_file`, `bash` and
`run_python` and earns 1 on every seed tried (150 seeds per task offline); an empty submit, the right content
passed only as the answer, an empty file, a symlinked deliverable and a wrong file all earn 0. `openenv validate`
passes and every task replays to a terminal reward over WebSocket with the new tools.

Source: https://github.com/nice-bills/shiftdesk
