"""Math: counting problems that need a short exact program."""
from math import gcd

from ..grading import exact_int
from .base import Built

DOMAIN = "mathematics-or-formal-reasoning"
NAME = "exact-count"

MOD = 1_000_000_007


def _lcm(a, b):
    return a * b // gcd(a, b)


def build(level, rng):
    if level == 1:
        while True:
            a, b, c = rng.sample([3, 4, 5, 6, 7, 9, 11, 13, 14, 15], 3)
            if c % a and c % b:
                break
        n = rng.randint(200_000, 3_000_000)
        ab, ac, bc = _lcm(a, b), _lcm(a, c), _lcm(b, c)
        either = n // a + n // b - n // ab
        with_c = n // ac + n // bc - n // _lcm(ab, c)
        target = either - with_c
        return Built(
            question=(
                f"How many integers x with 1 <= x <= {n} are divisible by {a} or by {b}, but not divisible by {c}?"
            ),
            files={},
            check=lambda v: exact_int(v, target),
            answer=target,
            answer_hint="an integer",
            budget=6,
            wrong=[n // a + n // b - n // _lcm(a, b), target + n // _lcm(_lcm(a, b), c)],
        )
    if level == 2:
        h, w = rng.randint(9, 14), rng.randint(9, 14)
        grid = [["." for _ in range(w)] for _ in range(h)]
        for _ in range(int(h * w * 0.18)):
            r, c = rng.randrange(h), rng.randrange(w)
            if (r, c) not in ((0, 0), (h - 1, w - 1)):
                grid[r][c] = "#"
        ways = [[0] * w for _ in range(h)]
        for r in range(h):
            for c in range(w):
                if grid[r][c] == "#":
                    continue
                if r == 0 and c == 0:
                    ways[r][c] = 1
                    continue
                ways[r][c] = (ways[r - 1][c] if r else 0) + (ways[r][c - 1] if c else 0)
        target = ways[h - 1][w - 1]
        text = "\n".join("".join(row) for row in grid) + "\n"
        return Built(
            question=(
                "grid.txt is a map: '.' is open, '#' is blocked. Moving only right or down one cell at a time, "
                "how many paths go from the top-left cell to the bottom-right cell without entering a blocked cell? "
                "Give the exact integer (0 if none)."
            ),
            files={"grid.txt": text},
            check=lambda v: exact_int(v, target),
            answer=target,
            answer_hint="an integer",
            budget=8,
            wrong=[target + 1],
        )
    n = rng.randint(25, 60)
    s = rng.randint(n * 2, n * 6)
    banned = rng.randint(0, 9)
    allowed = [d for d in range(10) if d != banned]
    # dp over digits; no leading zero
    dp = [0] * (s + 1)
    for d in allowed:
        if d != 0 and d <= s:
            dp[d] += 1
    for _ in range(n - 1):
        nxt = [0] * (s + 1)
        for tot, ways in enumerate(dp):
            if ways:
                for d in allowed:
                    if tot + d <= s:
                        nxt[tot + d] = (nxt[tot + d] + ways) % MOD
        dp = nxt
    target = dp[s] % MOD
    return Built(
        question=(
            f"Count the {n}-digit positive integers (no leading zero) whose digits sum to {s} and that never use "
            f"the digit {banned}. Give the count modulo 1000000007."
        ),
        files={},
        check=lambda v: exact_int(v, target),
        answer=target,
        answer_hint="an integer",
        budget=8,
        wrong=[(target + 1) % MOD],
    )
