"""Helpers for v4 file-deliverable tasks: the policy writes a file, hidden checks grade it.

Every check takes the deliverable's text (or None) and returns 1.0 only when all
of its checks pass, else 0.0.
"""
import csv
import io
import json
import re
from fractions import Fraction

from ..grading import to_number


def parse_json(text):
    if not isinstance(text, str):
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        return json.loads(t)
    except ValueError:
        return None


def parse_csv(text):
    """Rows as dicts with lower-cased, stripped header names and stripped values."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        rd = csv.reader(io.StringIO(text.strip().lstrip("\ufeff")))
        rows = [r for r in rd if any(c.strip() for c in r)]
    except csv.Error:
        return None
    if len(rows) < 1:
        return None
    head = [h.strip().lower() for h in rows[0]]
    out = []
    for r in rows[1:]:
        if len(r) != len(head):
            return None
        out.append({h: c.strip() for h, c in zip(head, r)})
    return out


def num(v):
    if isinstance(v, str) and not v.strip():
        return None
    return to_number(v)


def near(got, want, rel=0.01, abs_tol=1e-9):
    g = num(got)
    if g is None:
        return False
    return abs(g - want) <= max(abs_tol, abs(want) * rel) + 1e-12


def frac(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return Fraction(v)
    if isinstance(v, str):
        try:
            return Fraction(v.strip().replace(" ", ""))
        except (ValueError, ZeroDivisionError):
            return None
    return None


def graded(fn):
    """Wrap a check so any exception or a non-string deliverable scores 0."""
    def check(text):
        if not isinstance(text, str) or not text.strip():
            return 0.0
        try:
            return 1.0 if fn(text) else 0.0
        except Exception:
            return 0.0
    return check


def rows_to_csv(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def keyed(rows, key):
    out = {}
    for r in rows:
        k = r.get(key)
        if k is None or k in out:
            return None
        out[k] = r
    return out


_WS = re.compile(r"\s+")


def squash(s):
    return _WS.sub(" ", s).strip()
