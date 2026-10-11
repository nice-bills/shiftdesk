"""Media: subtitle timing and style checks on an SRT file."""
from ..grading import close, same_int_set, same_text
from .base import Built

DOMAIN = "media-content-production"
NAME = "subtitle-qc"

SPEAKERS = ["ANA", "BEN", "CLEO", "DEV"]
WORDS = ("we should leave before the storm hits the bridge again tonight but nobody listens to me "
         "anyway where did you put the keys I told you twice already the market closes early on "
         "sundays so hurry up please and bring the blue bag from the car").split()


def _ts(ms):
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _cues(rng, n):
    t = rng.randint(1000, 60000)
    cues = []
    for i in range(n):
        t += rng.randint(200, 3000)
        words = rng.sample(WORDS, rng.randint(3, 11))
        text = " ".join(words).capitalize()
        speaker = rng.choice(SPEAKERS)
        dur = rng.randint(700, 4200)
        cues.append({"n": i + 1, "start": t, "end": t + dur, "speaker": speaker, "text": text})
        t += dur
    return cues


def _render(cues):
    blocks = []
    for c in cues:
        blocks.append(f"{c['n']}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{c['speaker']}: {c['text']}\n")
    return "\n".join(blocks)


def build(level, rng):
    n = {1: 18, 2: 26, 3: 32}[level]
    cues = _cues(rng, n)
    if level == 1:
        who = rng.choice(SPEAKERS)
        total = sum(c["end"] - c["start"] for c in cues if c["speaker"] == who) / 1000
        return Built(
            question=(
                f"episode.srt is a subtitle file; each line starts with the speaker's name. What is the total time, "
                f"in seconds, that {who}'s subtitles are on screen? Give 3 decimals."
            ),
            files={"episode.srt": _render(cues)},
            check=lambda a: close(a, total, abs_tol=0.0005),
            answer=round(total, 3),
            answer_hint="a number such as 41.250",
            budget=8,
            wrong=[round(sum(1 for c in cues if c["speaker"] == who), 3)],
        )
    if level == 2:
        k = rng.randint(5, n - 5)
        shift = rng.choice([-1, 1]) * rng.randint(250, 2400)
        cut = rng.randint(k + 2, n - 1)
        note = (
            f"Editor notes\n1. Cue {cut} was cut from the edit: delete it and renumber nothing.\n"
            f"2. Every cue numbered greater than {k} must move by {shift:+d} ms (start and end).\n"
        )
        kept = [c for c in cues if c["n"] != cut]
        last = kept[-1]
        end = last["end"] + (shift if last["n"] > k else 0)
        target = _ts(end)
        return Built(
            question=(
                "Apply notes.txt to episode.srt. What is the end timestamp of the last remaining cue after the edit? "
                "Answer in SRT form HH:MM:SS,mmm."
            ),
            files={"episode.srt": _render(cues), "notes.txt": note},
            check=lambda a: same_text(a, target),
            answer=target,
            answer_hint='a string such as "00:03:12,480"',
            budget=10,
            wrong=[_ts(cues[-1]["end"])],
        )
    limit = 17
    guide = (
        "Style guide\n"
        f"- Reading speed must not exceed {limit} characters per second.\n"
        "- Count characters of the dialogue only: drop the speaker label and the colon and the space after it, "
        "then count every remaining character except spaces.\n"
        "- Seconds = (end - start) in milliseconds / 1000.\n"
    )
    # push some cues over the limit
    for c in rng.sample(cues, 6):
        chars = len(c["text"].replace(" ", ""))
        c["end"] = c["start"] + max(300, int(chars / rng.uniform(17.5, 26) * 1000))
    # keep cue order consistent
    for a, b in zip(cues, cues[1:]):
        if b["start"] < a["end"]:
            shift = a["end"] - b["start"] + 100
            for c in cues[cues.index(b):]:
                c["start"] += shift
                c["end"] += shift
    bad = {c["n"] for c in cues if len(c["text"].replace(" ", "")) / ((c["end"] - c["start"]) / 1000) > limit}
    with_label = {
        c["n"] for c in cues
        if len((c["speaker"] + ": " + c["text"]).replace(" ", "")) / ((c["end"] - c["start"]) / 1000) > limit
    }
    return Built(
        question=(
            "Check episode.srt against style.txt. Which cue numbers break the reading-speed rule? Answer with the "
            "cue numbers in increasing order, separated by commas (empty string if none)."
        ),
        files={"episode.srt": _render(cues), "style.txt": guide},
        check=lambda a: same_int_set(a, bad) if bad else (1.0 if str(a).strip() in ("", "[]") else 0.0),
        answer=",".join(str(x) for x in sorted(bad)),
        answer_hint='a string such as "3,8,15"',
        budget=12,
        wrong=[",".join(str(x) for x in sorted(with_label))] if with_label != bad else [],
    )
