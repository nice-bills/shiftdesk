"""Answer checks shared by the families."""
import re

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def to_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and len(value) == 1:
        return to_number(next(iter(value.values())))
    if isinstance(value, str):
        text = value.replace(",", "").replace("$", "").replace("%", "").strip()
        found = _NUM.findall(text)
        if len(found) == 1:
            try:
                return float(found[0])
            except ValueError:
                return None
    return None


def close(value, target: float, rel: float = 0.0, abs_tol: float = 0.0) -> float:
    got = to_number(value)
    if got is None:
        return 0.0
    tol = max(abs_tol, abs(target) * rel)
    return 1.0 if abs(got - target) <= tol + 1e-12 else 0.0


def exact_int(value, target: int) -> float:
    got = to_number(value)
    if got is None or got != int(got):
        return 0.0
    return 1.0 if int(got) == target else 0.0


def norm_text(value) -> str:
    if isinstance(value, dict) and len(value) == 1:
        value = next(iter(value.values()))
    if not isinstance(value, str):
        value = str(value)
    return value.strip().strip("\"'`.").strip().lower()


def same_text(value, target: str) -> float:
    return 1.0 if norm_text(value) == target.strip().lower() else 0.0


def same_int_set(value, target: set) -> float:
    if isinstance(value, dict) and len(value) == 1:
        value = next(iter(value.values()))
    if isinstance(value, str):
        items = [x for x in re.split(r"[\s,;]+", value.strip("[]() ")) if x]
    elif isinstance(value, list):
        items = value
    else:
        return 0.0
    got = set()
    for item in items:
        num = to_number(item)
        if num is None or num != int(num):
            return 0.0
        got.add(int(num))
    return 1.0 if got == set(target) else 0.0


# ---- v3 helpers: structured answers, all-or-nothing
import json as _json
from fractions import Fraction as _Fraction


def load(value):
    """Turn a JSON string answer into a value; leave other values alone."""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        if text[:1] in "[{":
            try:
                return _json.loads(text)
            except ValueError:
                return value
    return value


def fields(value, checks: dict) -> float:
    """All-or-nothing: value must be an object with every key in checks passing."""
    value = load(value)
    if not isinstance(value, dict):
        return 0.0
    norm = {str(k).strip().lower(): v for k, v in value.items()}
    for key, check in checks.items():
        if key.lower() not in norm:
            return 0.0
        try:
            if check(norm[key.lower()]) != 1.0:
                return 0.0
        except Exception:
            return 0.0
    return 1.0


def as_list(value):
    value = load(value)
    if isinstance(value, dict) and len(value) == 1:
        value = load(next(iter(value.values())))
    if isinstance(value, str):
        text = value.strip().strip("[]()")
        return [x.strip().strip("\"'") for x in re.split(r"[,;\n]+", text) if x.strip().strip("\"'")]
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value]
    return None


def same_list(value, target, ordered=False, case=False) -> float:
    got = as_list(value)
    if got is None:
        return 0.0
    tgt = [str(x) for x in target]
    if not case:
        got = [g.lower() for g in got]
        tgt = [t.lower() for t in tgt]
    if ordered:
        return 1.0 if got == tgt else 0.0
    return 1.0 if sorted(got) == sorted(tgt) and len(set(got)) == len(got) else 0.0


def same_fraction(value, target) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        if isinstance(value, int):
            got = _Fraction(value)
        elif isinstance(value, str):
            got = _Fraction(value.strip().replace(" ", ""))
        else:
            return 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0
    return 1.0 if got == _Fraction(target) else 0.0


def same_bool(value, target: bool) -> float:
    if isinstance(value, bool):
        return 1.0 if value == target else 0.0
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "yes", "no"):
        return 1.0 if (value.strip().lower() in ("true", "yes")) == target else 0.0
    return 0.0
