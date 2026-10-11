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
