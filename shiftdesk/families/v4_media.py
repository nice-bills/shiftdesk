"""Media and content production v4: subtitle retiming, image and audio asset audits, markdown to HTML."""
import io
import json
import math
import re
import struct
import wave
from html.parser import HTMLParser

from .base import Built
from .filetask import graded, keyed, parse_csv, parse_json, rows_to_csv

DOMAIN = "media-content-production"

LINES = ["Where did you put the keys?", "I left them on the table.", "We should go before it rains.",
         "Nobody told me the train was cancelled.", "Hold the door!", "That's not what I meant.",
         "Give me five minutes.", "Is anyone else hearing that?", "Turn left at the bridge.",
         "You never listen.", "It's colder than yesterday.", "Can you call me back tonight?",
         "I think we're lost.", "The meeting moved to Thursday.", "Bring the blue folder.",
         "Did you lock the car?", "He's been gone for an hour.", "Let's take the long way home.",
         "Keep your voice down.", "We still have time.", "I found it under the seat.", "Look at the sky."]


def _ts(ms):
    ms = int(ms)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _parse_ts(s):
    m = re.fullmatch(r"\s*(\d+):(\d\d):(\d\d)[,.](\d{1,3})\s*", s)
    if not m:
        return None
    h, mi, se, ms = m.groups()
    return ((int(h) * 60 + int(mi)) * 60 + int(se)) * 1000 + int(ms.ljust(3, "0"))


def parse_srt(text):
    if not isinstance(text, str):
        return None
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    cues = []
    for b in blocks:
        ls = [l for l in b.split("\n")]
        if len(ls) < 3 or not ls[0].strip().isdigit() or "-->" not in ls[1]:
            return None
        a, c = ls[1].split("-->", 1)
        s, e = _parse_ts(a), _parse_ts(c)
        if s is None or e is None:
            return None
        cues.append((int(ls[0].strip()), s, e, "\n".join(l.rstrip() for l in ls[2:])))
    return cues


def _srt(cues):
    return "\n".join(f"{i}\n{_ts(s)} --> {_ts(e)}\n{t}\n" for i, (s, e, t) in enumerate(cues, 1))


# --------------------------------------------------------------------------- subtitle retime
class SrtRetime:
    NAME = "srt-retime"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        n = rng.randint(10, 16)
        t = rng.randint(500, 4000)
        cues = []
        for i in range(n):
            t += rng.randint(300, 2500)
            d = rng.randint(900, 3800)
            txt = rng.choice(LINES)
            if rng.random() < 0.3:
                txt += "\n" + rng.choice(LINES)
            cues.append((t, t + d, txt))
            t += d
        if level == 1:
            sign = rng.choice([-1, 1])
            off = rng.randint(300, 4500) * sign
            if sign < 0:
                off = max(off, -cues[0][0] + 50)
            new = [(s + off, e + off, x) for s, e, x in cues]
            q = (f"subs.srt is {abs(off)} ms {'late' if off < 0 else 'early'} against the video: every subtitle must be "
                 f"shown {abs(off)} ms {'earlier' if off < 0 else 'later'}. Write the corrected file to output/out.srt "
                 "(same cues and text, standard SRT timestamps HH:MM:SS,mmm).")
            files = {"subs.srt": _srt(cues)}
            wrong = [_srt([(s - off, e - off, x) for s, e, x in cues]), _srt(cues)]
        else:
            # 25 fps source retimed for 23.976 fps video plus an offset, found from two sync points
            ratio = rng.choice([25 / 23.976, 23.976 / 25, 1.001, 1 / 1.001])
            off = rng.randint(-6000, 6000)
            mapf = lambda x: int(math.floor(x * ratio + off + 0.5))
            a, b = rng.sample(range(2, n - 2), 2)
            a, b = min(a, b), max(a, b)
            # credits: drop cues tagged as credits, and cues whose mapped end <= 0
            tagged = rng.sample([i for i in range(n) if i not in (a, b)], 2)
            src = []
            for i, (s, e, x) in enumerate(cues):
                if i in tagged:
                    x = "[" + rng.choice(["SUBTITLES BY OPENSUBS", "Sync & corrections by XYZ", "ADVERTISE YOUR PRODUCT HERE"]) + "]"
                src.append((s, e, x))
            if off < 0:
                # make the first cue map to before zero
                s0 = int(rng.randint(100, 400))
                src[0] = (s0, s0 + 300, "[SUBTITLES BY OPENSUBS]")
                if 0 not in tagged:
                    tagged.append(0)
            sync = (f"Sync points measured against the new video:\n"
                    f"- cue {a + 1} (\"{src[a][2].splitlines()[0]}\") must START at {_ts(mapf(src[a][0]))}\n"
                    f"- cue {b + 1} (\"{src[b][2].splitlines()[0]}\") must START at {_ts(mapf(src[b][0]))}\n")
            exact_a, exact_b = mapf(src[a][0]), mapf(src[b][0])
            # the linear map through the two sync points (what the solver can recover)
            k = (exact_b - exact_a) / (src[b][0] - src[a][0])
            lin = lambda x: int(math.floor(exact_a + (x - src[a][0]) * k + 0.5))
            new = []
            for i, (s, e, x) in enumerate(src):
                if x.startswith("[") and x.endswith("]"):
                    continue
                ns, ne = lin(s), lin(e)
                if ne <= 0:
                    continue
                new.append((max(ns, 0), ne, x))
            files = {"subs.srt": _srt(src), "sync.txt": sync,
                     "style.md": "Delivery rules:\n- Retime every cue with ONE linear map (new = a * old + b) fitted exactly "
                                 "through the two sync points; apply it to start and end times and round to the nearest "
                                 "millisecond.\n- Remove credit/advert cues: cues whose whole text is in square brackets.\n"
                                 "- Drop any cue that would end at or before 00:00:00,000; clamp a negative start to 0.\n"
                                 "- Renumber the remaining cues from 1.\n"}
            q = ("Retime subs.srt for the new video cut using sync.txt and style.md, and write the deliverable "
                 "subtitle file to output/out.srt.")
            wrong = [_srt([(s + off, e + off, x) for s, e, x in src]), _srt([(lin(s), lin(e), x) for s, e, x in src])]
        answer = _srt(new)

        def check(text, new=new):
            got = parse_srt(text)
            if got is None or len(got) != len(new):
                return False
            for j, ((num, s, e, x), (ws, we, wx)) in enumerate(zip(got, new), 1):
                if num != j or abs(s - ws) > 1 or abs(e - we) > 1 or x.strip() != wx.strip():
                    return False
            return True

        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/out.srt", budget=14 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/out.srt")


# --------------------------------------------------------------------------- image audit
def _img_bytes(fmt, w, h, color, orientation=None):
    from PIL import Image
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    if fmt == "JPEG":
        kw = {"quality": 70}
        if orientation:
            ex = Image.Exif()
            ex[0x0112] = orientation
            kw["exif"] = ex.tobytes()
        im.save(buf, "JPEG", **kw)
    elif fmt == "PNG":
        im.save(buf, "PNG", optimize=False)
    elif fmt == "GIF":
        im.convert("P").save(buf, "GIF")
    elif fmt == "WEBP":
        im.save(buf, "WEBP", quality=60, method=0)
    return buf.getvalue()


class ImageAudit:
    NAME = "image-audit"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        n = rng.randint(5, 7)
        slots = rng.sample(["hero", "thumb", "avatar", "banner", "card", "logo", "gallery-1", "gallery-2", "promo"], n)
        spec = {"max_w": rng.choice([800, 1000, 1200]), "max_h": rng.choice([600, 800]), "formats": ["JPEG", "PNG", "WEBP"]}
        spec["max_w"], spec["max_h"] = spec["max_w"] // 4, spec["max_h"] // 4
        files, truth = {}, {}
        rotated_any = False
        for i, slot in enumerate(slots):
            fmt = rng.choice(["JPEG", "PNG", "PNG", "JPEG", "GIF"] + (["WEBP"] if level == 2 else []))
            w = rng.randint(40, spec["max_w"] + 80)
            h = rng.randint(40, spec["max_h"] + 80)
            orient = None
            if level == 2 and fmt == "JPEG" and (not rotated_any or rng.random() < 0.3):
                orient = rng.choice([6, 8])
                rotated_any = True
            ext = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp"}[fmt]
            if level == 2 and rng.random() < 0.3:
                ext = rng.choice([e for e in (".jpg", ".png", ".gif") if e != ext])
            name = f"assets/{slot}{ext}"
            data = _img_bytes(fmt, w, h, (rng.randrange(256), rng.randrange(256), rng.randrange(256)), orient)
            files[name] = data
            dw, dh = (h, w) if orient in (6, 8) else (w, h)
            reasons = []
            if fmt not in spec["formats"]:
                reasons.append("format")
            if dw > spec["max_w"] or dh > spec["max_h"]:
                reasons.append("size")
            if level == 2 and ext.lstrip(".").replace("jpg", "jpeg").upper() != fmt:
                reasons.append("extension")
            truth[name] = {"format": fmt, "width": dw, "height": dh, "ok": not reasons, "reasons": reasons}
        guide = [f"# Web asset spec", f"- Allowed formats: {', '.join(spec['formats'])}.",
                 f"- Displayed size must fit within {spec['max_w']} x {spec['max_h']} px (width x height)."]
        if level == 2:
            guide += ["- Displayed size accounts for EXIF orientation: orientations 5-8 rotate the image by 90 degrees, so "
                      "width and height swap.",
                      "- The file extension must match the real format (.jpg/.jpeg for JPEG, .png, .gif, .webp); the "
                      "format is what the file's bytes say, not its name."]
        guide.append("- Reason codes, in this order: " + ", ".join(["format", "size"] + (["extension"] if level == 2 else [])) + ".")
        files["spec.md"] = "\n".join(guide) + "\n"
        q = ("Audit every image under assets/ against spec.md. Write output/report.csv with columns "
             "file,format,width,height,ok,reasons: file as listed (e.g. assets/hero.jpg), format as JPEG/PNG/GIF/WEBP, "
             "displayed width and height in px, ok as true/false, and reasons as the failing reason codes joined by ';' "
             "in spec order (empty when ok).")
        header = ["file", "format", "width", "height", "ok", "reasons"]
        answer = rows_to_csv(header, [[k, v["format"], v["width"], v["height"], str(v["ok"]).lower(), ";".join(v["reasons"])]
                                      for k, v in sorted(truth.items())])

        def check(text, truth=truth):
            got = keyed(parse_csv(text), "file")
            if got is None or set(got) != set(truth):
                return False
            for k, v in truth.items():
                r = got[k]
                if r.get("format", "").upper().replace("JPG", "JPEG") != v["format"]:
                    return False
                if r.get("width") != str(v["width"]) or r.get("height") != str(v["height"]):
                    return False
                if r.get("ok", "").lower() not in ("true", "false") or (r["ok"].lower() == "true") != v["ok"]:
                    return False
                if [x.strip() for x in r.get("reasons", "").split(";") if x.strip()] != v["reasons"]:
                    return False
            return True

        raw = {k: dict(v) for k, v in truth.items()}
        for k, v in raw.items():
            f = files[k]
            from PIL import Image
            with Image.open(io.BytesIO(f)) as im:
                v["width"], v["height"] = im.size
        wrong = [rows_to_csv(header, [[k, v["format"], v["width"], v["height"], str(v["ok"]).lower(), ";".join(v["reasons"])]
                                      for k, v in sorted(raw.items())]),
                 rows_to_csv(header, [[k, v["format"], v["width"], v["height"], "true", ""] for k, v in sorted(truth.items())])]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/report.csv", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/report.csv")


# --------------------------------------------------------------------------- audio audit
def _wav(rate, ch, width, frames_data):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(frames_data)
    return buf.getvalue()


class AudioAudit:
    NAME = "audio-audit"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        n = rng.randint(4, 6)
        names = rng.sample(["intro", "vo_take1", "vo_take2", "sting", "outro", "ambience", "sfx_door", "music_bed"], n)
        target_rate = rng.choice([44100, 48000])
        files, truth = {}, {}
        clip_forced = False
        for nm in names:
            rate = rng.choice([8000, 11025, 16000, target_rate // 4]) if level == 1 else rng.choice([8000, 12000, 16000, 11025])
            ch = rng.choice([1, 2])
            width = 2
            dur_frames = int(rate * rng.uniform(0.3, 1.2))
            amp = rng.uniform(0.1, 0.95)
            clip = level == 2 and (not clip_forced or rng.random() < 0.3)
            clip_forced |= clip
            f0 = rng.choice([220, 330, 440, 550, 660])
            vals = []
            for i in range(dur_frames):
                v = amp * math.sin(2 * math.pi * f0 * i / rate)
                if clip:
                    v *= 1.6
                vals.append(int(round(max(-1.0, min(1.0, v)) * 32767)))
            peak = max(abs(x) for x in vals)
            clipped = sum(1 for x in vals if x >= 32767 or x <= -32767)
            if ch == 1:
                inter = vals
            else:
                inter = [y for x in vals for y in (x, x // 2)]
            data = struct.pack(f"<{len(inter)}h", *inter)
            files[f"audio/{nm}.wav"] = _wav(rate, ch, width, bytes(data))
            dur = dur_frames / rate
            pk = 20 * math.log10(peak / 32768) if peak else -120.0
            truth[f"audio/{nm}.wav"] = {"sample_rate": rate, "channels": ch, "duration_s": dur, "peak_dbfs": pk,
                                        "clipped_samples": clipped, "clipping": clipped >= 3}
        rules = ["# Audio deliverable spec (16-bit PCM WAV)",
                 "- duration_s = frames / sample_rate, to 3 decimals.",
                 "- peak_dbfs = 20*log10(max |sample| / 32768) over all channels, to 2 decimals."]
        if level == 2:
            rules += ["- A sample is clipped when its value is 32767 or -32767 or lower (count over every channel separately).",
                      "- clipping is true when a file has 3 or more clipped samples."]
        files["spec.md"] = "\n".join(rules) + "\n"
        cols = ["file", "sample_rate", "channels", "duration_s", "peak_dbfs"] + (["clipped_samples", "clipping"] if level == 2 else [])
        # count clipped across channels: channel 2 is half amplitude so never clips
        q = ("Measure every WAV under audio/ as spec.md defines and write output/audio_report.csv with columns "
             + ",".join(cols) + " (one row per file, file as listed, e.g. audio/intro.wav"
             + ("; clipping as true/false" if level == 2 else "") + ").")

        def row(k, v):
            r = [k, v["sample_rate"], v["channels"], f"{v['duration_s']:.3f}", f"{v['peak_dbfs']:.2f}"]
            if level == 2:
                r += [v["clipped_samples"], str(v["clipping"]).lower()]
            return r

        answer = rows_to_csv(cols, [row(k, v) for k, v in sorted(truth.items())])

        def check(text, truth=truth):
            got = keyed(parse_csv(text), "file")
            if got is None or set(got) != set(truth):
                return False
            for k, v in truth.items():
                r = got[k]
                if r.get("sample_rate") != str(v["sample_rate"]) or r.get("channels") != str(v["channels"]):
                    return False
                if abs(float(r.get("duration_s", "nan")) - v["duration_s"]) > 0.0015:
                    return False
                if abs(float(r.get("peak_dbfs", "nan")) - v["peak_dbfs"]) > 0.02:
                    return False
                if level == 2:
                    if r.get("clipped_samples") != str(v["clipped_samples"]):
                        return False
                    if r.get("clipping", "").lower() != str(v["clipping"]).lower():
                        return False
            return True

        w1 = {k: {**v, "duration_s": v["duration_s"] * v["channels"]} for k, v in truth.items()}
        w2 = {k: {**v, "peak_dbfs": 20 * math.log10(10 ** (v["peak_dbfs"] / 20) * 32768 / 32767) + 0.5} for k, v in truth.items()}
        wrong = [rows_to_csv(cols, [row(k, v) for k, v in sorted(w1.items())]),
                 rows_to_csv(cols, [row(k, v) for k, v in sorted(w2.items())])]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/audio_report.csv", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/audio_report.csv")


# --------------------------------------------------------------------------- markdown to html
class _Tok(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        self.out.append(("start", tag, tuple(sorted((k, " ".join(sorted((v or "").split())) if k == "rel" else (v or "")) for k, v in attrs))))

    def handle_endtag(self, tag):
        self.out.append(("end", tag))

    def handle_data(self, data):
        d = re.sub(r"\s+", " ", data)
        if d.strip():
            if self.out and self.out[-1][0] == "data":
                self.out[-1] = ("data", self.out[-1][1] + d)
            else:
                self.out.append(("data", d))


def html_tokens(text):
    p = _Tok()
    p.feed(text)
    p.close()
    toks = []
    for t in p.out:
        if t[0] == "data":
            t = ("data", t[1].strip())
        toks.append(t)
    # whitespace at tag boundaries is not significant
    return [t for t in toks if not (t[0] == "data" and not t[1])]


TOPICS = ["Release Notes", "Getting Started", "Field Recording Tips", "Color Grading Basics", "Podcast Checklist",
          "Interview Setup", "Export Settings", "Archive Policy"]
WORDS = ["clean", "audio", "levels", "light", "frame", "edit", "timeline", "render", "camera", "tripod", "noise", "gain",
         "proxy", "codec", "backup", "storage", "client", "review", "draft", "cut"]


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _slug(s):
    s = re.sub(r"[^a-z0-9\s-]", "", s.lower())
    return re.sub(r"[\s-]+", "-", s).strip("-")


class MarkdownHtml:
    NAME = "markdown-html"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        def sentence():
            ws = rng.sample(WORDS, rng.randint(4, 8))
            return " ".join(ws).capitalize()

        def inline():
            parts = []
            html = []
            for _ in range(rng.randint(2, 4)):
                k = rng.random()
                s = sentence()
                if k < 0.25:
                    w = rng.choice(WORDS)
                    parts.append(f"{s} **{w}**.")
                    html.append(f"{_esc(s)} <strong>{w}</strong>.")
                elif k < 0.45:
                    url = rng.choice([f"https://example.com/{rng.choice(WORDS)}", f"/docs/{rng.choice(WORDS)}",
                                      f"https://media.test/{rng.choice(WORDS)}?ref=1&x=2"])
                    label = rng.choice(WORDS) + " guide"
                    parts.append(f"{s} [{label}]({url}).")
                    ext = url.startswith("http")
                    attrs = f' href="{_esc(url).replace(chr(34), "&quot;")}"'
                    if level == 2 and ext:
                        attrs += ' target="_blank" rel="noopener noreferrer"'
                    html.append(f"{_esc(s)} <a{attrs}>{_esc(label)}</a>.")
                elif k < 0.6 and level == 2:
                    w = rng.choice(WORDS)
                    parts.append(f"{s} *{w}*.")
                    html.append(f"{_esc(s)} <em>{w}</em>.")
                elif k < 0.7:
                    parts.append(f"{s} & more.")
                    html.append(f"{_esc(s)} &amp; more.")
                else:
                    parts.append(s + ".")
                    html.append(_esc(s) + ".")
            return " ".join(parts), " ".join(html)

        md, html = [], []
        title = rng.choice(TOPICS)
        used_ids = {}

        def heading(level_n, text):
            md.append("#" * level_n + " " + text)
            tag = f"h{level_n}"
            if level == 2:
                if level_n == 1 and any(h.startswith("<h1") for h in html):
                    tag = "h2"
                sid = _slug(text)
                if sid in used_ids:
                    used_ids[sid] += 1
                    sid = f"{sid}-{used_ids[sid]}"
                else:
                    used_ids[sid] = 1
                html.append(f'<{tag} id="{sid}">{_esc(text)}</{tag}>')
            else:
                html.append(f"<{tag}>{_esc(text)}</{tag}>")
            md.append("")

        heading(1, title)
        secs = rng.sample(["Overview", "Before You Start", "Steps", "Notes", "Overview", "Gear List", "FAQ"], rng.randint(3, 4))
        for sname in secs:
            heading(rng.choice([2, 2, 3]) if level == 1 else rng.choice([2, 2, 3, 1]), sname)
            for _ in range(rng.randint(1, 2)):
                if rng.random() < 0.4:
                    items = [inline() for _ in range(rng.randint(2, 4))]
                    md += [f"- {m}" for m, _ in items]
                    html.append("<ul>" + "".join(f"<li>{h}</li>" for _, h in items) + "</ul>")
                else:
                    m1, h1 = inline()
                    m2, h2 = inline()
                    md += [m1, m2]  # two source lines, one paragraph
                    html.append(f"<p>{h1} {h2}</p>")
                md.append("")
        files = {"article.md": "\n".join(md).rstrip() + "\n"}
        rules = ["# Markdown subset and HTML house style",
                 "- '# ' to '###### ' start headings h1-h6. Consecutive non-blank lines form one <p>; a blank line ends it.",
                 "- A run of consecutive lines starting with '- ' forms one <ul> with an <li> per line (a blank line ends the list).",
                 "- **text** becomes <strong>text</strong>; [label](url) becomes <a href=\"url\">label</a>.",
                 "- Escape &, < and > in text as &amp;, &lt; and &gt;.",
                 "- Output only the body fragment (no <html>, <head> or <body>)."]
        if level == 2:
            rules += ["- *text* becomes <em>text</em>.",
                      "- Only the first h1 stays h1; any later '# ' heading becomes h2.",
                      "- Every heading gets id = slug of its text: lowercase, drop characters other than a-z, 0-9, spaces "
                      "and hyphens, turn runs of spaces/hyphens into one hyphen. Repeated slugs get -2, -3, ...",
                      "- Links whose url starts with http:// or https:// also get target=\"_blank\" rel=\"noopener noreferrer\"."]
        files["style.md"] = "\n".join(rules) + "\n"
        answer = "\n".join(html) + "\n"
        q = "Convert article.md to HTML following style.md exactly and write it to output/article.html."
        want = html_tokens(answer)

        def check(text, want=want):
            return html_tokens(text) == want

        wrong = [answer.replace("<strong>", "<b>").replace("</strong>", "</b>"),
                 re.sub(r' (target|rel)="[^"]*"', "", answer), re.sub(r' id="[^"]*"', "", answer),
                 answer.replace("&amp;", "&")]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/article.html", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/article.html")
