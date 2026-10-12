"""Media and content production v3 families: edit timelines and headline style checks."""
import re

from ..grading import exact_int, fields, same_list, same_text
from .base import Built

DOMAIN = "media-content-production"


def _tc(frames, fps):
    f = frames % fps
    s = frames // fps
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


class EditTimeline:
    NAME = "edit-timeline"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        fps = rng.choice([24, 25, 30])
        clips = []
        for i in range(rng.randint(6, 10)):
            start = rng.randint(0, 3000 * fps)
            dur = rng.randint(2 * fps, 40 * fps)
            clips.append([f"C{i + 1:02d}", start, start + dur])  # source in, out (exclusive)
        notes = []
        final = [list(c) for c in clips]
        if level == 2:
            drop = rng.choice(final)
            final = [c for c in final if c is not drop]
            notes.append(f"- Director: drop {drop[0]} entirely.")
            trim = rng.choice(final)
            t = rng.randint(fps // 2, 3 * fps)
            trim[2] -= t
            notes.append(f"- Trim {t} frames off the end of {trim[0]}.")
            notes.append(f"- Add a {fps * 2}-frame black slug at the very start of the timeline.")
        total = sum(c[2] - c[1] for c in final) + (fps * 2 if level == 2 else 0)
        naive = sum(c[2] - c[1] for c in clips)
        edl = [f"TITLE: promo cut  FPS: {fps}", "# source_in and source_out are timecodes HH:MM:SS:FF; "
               "source_out is exclusive (the frame at source_out is not used).", "clip,source_in,source_out"]
        edl += [f"{c[0]},{_tc(c[1], fps)},{_tc(c[2], fps)}" for c in clips]
        files = {"timeline.edl": "\n".join(edl) + "\n"}
        if level == 2:
            files["review_notes.txt"] = "Review notes for the next conform (apply all of them)\n" + "\n".join(notes) + "\n"
        q = ("Clips play back to back in the listed order. What is the total program length in frames, "
             "and as a timecode HH:MM:SS:FF at the timeline frame rate?")
        if level == 2:
            q = "After applying review_notes.txt: " + q[0].lower() + q[1:]
        return Built(
            question=q,
            files=files,
            check=lambda a: fields(a, {"frames": lambda v: exact_int(v, total),
                                       "timecode": lambda v: same_text(v, _tc(total, fps))}),
            answer={"frames": total, "timecode": _tc(total, fps)},
            answer_hint='a JSON object {"frames": 4321, "timecode": "00:02:52:21"}',
            budget=8,
            wrong=[{"frames": naive, "timecode": _tc(naive, fps)}] if level == 2 else
                  [{"frames": total + len(clips), "timecode": _tc(total + len(clips), fps)}],
        )


WORDS = ["city", "council", "votes", "new", "park", "budget", "storm", "hits", "coast", "local", "team", "wins",
         "final", "school", "opens", "library", "prices", "rise", "again", "market", "rally", "museum", "debuts",
         "exhibit", "transit", "plan", "delayed", "mayor", "unveils", "housing", "deal"]
BANNED = ["shocking", "unbelievable", "slams", "epic", "insane", "destroys"]
BRANDS = ["iPhone", "eBay", "YouTube", "PlayStation"]


class HeadlineStyle:
    NAME = "headline-style"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        maxlen = rng.choice([60, 65, 70])
        banned = rng.sample(BANNED, 3)

        def sentence_case(ws):
            return " ".join([ws[0].capitalize()] + ws[1:])

        heads = []
        for i in range(rng.randint(10, 14)):
            ws = rng.sample(WORDS, rng.randint(4, 9))
            kind = rng.random()
            if kind < 0.15:
                ws.insert(rng.randrange(len(ws)), rng.choice(banned))
            elif kind < 0.25:
                ws.insert(rng.randrange(len(ws)), rng.choice([b for b in BANNED if b not in banned]))
            if level == 2 and rng.random() < 0.3:
                ws.insert(rng.randrange(1, len(ws)), rng.choice(BRANDS))
            text = sentence_case(ws)
            if rng.random() < 0.15:
                text = " ".join(w.capitalize() for w in text.split())
            if rng.random() < 0.12:
                text += "."
            if rng.random() < 0.2:
                text += " " + " ".join(rng.sample(WORDS, 4))
            heads.append((f"H{i + 1:02d}", text))

        def violates(text, lvl):
            words = text.rstrip(".").split()
            if len(text) > maxlen:
                return True
            if text.endswith("."):
                return True
            if any(re.sub(r"\W", "", w).lower() in banned for w in words):
                return True
            for w in words[1:]:
                if w[0].isupper() and not (lvl == 2 and w in BRANDS):
                    return True
            if not words[0][0].isupper():
                return True
            return False

        bad = [h for h, t in heads if violates(t, level)]
        bad1 = [h for h, t in heads if violates(t, 1)]
        if not bad or len(bad) == len(heads) or (level == 2 and bad1 == bad):
            return HeadlineStyle.build(level, rng)
        guide = ["House style: headlines (page 1 of " + ("2" if level == 2 else "1") + ")",
                 f"1. At most {maxlen} characters, spaces included.",
                 "2. Sentence case: capitalize only the first word.",
                 "3. No full stop at the end.",
                 "4. Never use these words: " + ", ".join(banned) + "."]
        files = {"style_guide_p1.txt": "\n".join(guide) + "\n",
                 "headlines.tsv": "id\theadline\n" + "".join(f"{h}\t{t}\n" for h, t in heads)}
        if level == 2:
            files["style_guide_p2.txt"] = ("House style (page 2 of 2)\nException to rule 2: brand names keep their own "
                                           "capitalization anywhere in a headline: " + ", ".join(BRANDS) + ".\n")
        return Built(
            question="Which headlines in headlines.tsv break the house style guide? Read every page of the guide.",
            files=files,
            check=lambda a: fields(a, {"violations": lambda v: same_list(v, bad, case=True)}),
            answer={"violations": bad},
            answer_hint='a JSON object {"violations": ["H02", "H09"]} listing every breaking headline id',
            budget=8,
            wrong=[{"violations": bad1}] if level == 2 else [{"violations": bad[:-1]}],
        )
