"""Cybersecurity: find the brute-force login that worked, in an sshd log."""
from datetime import datetime, timedelta

from ..grading import same_text
from .base import Built

DOMAIN = "cybersecurity"
NAME = "auth-hunt"

USERS = ["admin", "deploy", "backup", "git", "oracle", "jenkins", "ubuntu", "postgres", "kofi", "mia"]


def _ip(rng, prefix=None):
    if prefix:
        return f"{prefix}.{rng.randint(2, 250)}"
    return f"{rng.choice([45, 61, 89, 103, 141, 176, 185, 193, 203, 212])}.{rng.randint(1, 254)}.{rng.randint(1, 254)}.{rng.randint(2, 250)}"


def build(level, rng):
    start = datetime(2026, rng.randint(1, 9), rng.randint(1, 27), rng.randint(0, 20), rng.randint(0, 59))
    events = []  # (time, ok, user, ip)
    window = 10
    threshold = 5

    def burst(ip_fn, user, n, t0, spread, success_after=None):
        t = t0
        for _ in range(n):
            t += timedelta(seconds=rng.randint(5, spread))
            events.append((t, False, user, ip_fn()))
        if success_after is not None:
            events.append((t + timedelta(seconds=success_after), True, user, ip_fn()))

    # background noise: normal users
    for _ in range(rng.randint(25, 45)):
        t = start + timedelta(seconds=rng.randint(0, 6 * 3600))
        ip = _ip(rng)
        user = rng.choice(USERS)
        if rng.random() < 0.25:
            events.append((t, False, user, ip))
            t += timedelta(seconds=rng.randint(4, 40))
        events.append((t, True, user, ip))
    span = 6 * 3600
    if level == 1:
        attacker = _ip(rng)
        burst(lambda: attacker, rng.choice(USERS), rng.randint(14, 30), start + timedelta(seconds=rng.randint(0, span)), 20)
        for _ in range(3):
            ip = _ip(rng)
            burst(lambda ip=ip: ip, rng.choice(USERS), rng.randint(3, 9), start + timedelta(seconds=rng.randint(0, span)), 30)
        answer = attacker
        q = "Which source IP has the most failed password attempts in auth.log? Answer with the IP address."
        budget = 8
    elif level == 2:
        attacker = _ip(rng)
        victim = rng.choice(USERS)
        burst(lambda: attacker, victim, rng.randint(6, 12), start + timedelta(seconds=rng.randint(0, span)), 50, rng.randint(20, 200))
        # decoy 1: more failures, never succeeds
        d1 = _ip(rng)
        burst(lambda: d1, rng.choice(USERS), rng.randint(15, 25), start + timedelta(seconds=rng.randint(0, span)), 20)
        # decoy 2: failures then success, but the success is outside the window
        d2 = _ip(rng)
        burst(lambda: d2, rng.choice(USERS), rng.randint(6, 9), start + timedelta(seconds=rng.randint(0, span)), 30, window * 60 + rng.randint(300, 1500))
        # decoy 3: success right after only a few failures
        d3 = _ip(rng)
        burst(lambda: d3, rng.choice(USERS), 3, start + timedelta(seconds=rng.randint(0, span)), 30, 30)
        answer = attacker
        q = (
            f"Find the compromise: a source IP with at least {threshold} failed passwords for one user within any "
            f"{window}-minute span, followed by an accepted login from that same IP for that same user no more than "
            f"{window} minutes after its last failure. Exactly one IP matches. Answer with that IP."
        )
        budget = 10
    else:
        prefix = f"{rng.choice([77, 91, 146, 194])}.{rng.randint(1, 254)}.{rng.randint(1, 254)}"
        victim = rng.choice(USERS)
        t0 = start + timedelta(seconds=rng.randint(0, span))
        n_fail = rng.randint(8, 14)
        burst(lambda: _ip(rng, prefix), victim, n_fail, t0, 40, rng.randint(20, 200))
        # decoy: one IP with many failures and no success
        d1 = _ip(rng)
        burst(lambda: d1, rng.choice(USERS), rng.randint(15, 25), start + timedelta(seconds=rng.randint(0, span)), 20)
        # decoy: subnet spread, but success is for a different user
        p2 = f"{rng.choice([23, 38, 152])}.{rng.randint(1, 254)}.{rng.randint(1, 254)}"
        u2 = rng.choice([u for u in USERS if u != victim])
        burst(lambda: _ip(rng, p2), u2, rng.randint(8, 12), start + timedelta(seconds=rng.randint(0, span)), 40)
        events.append((events[-1][0] + timedelta(seconds=60), True, rng.choice([u for u in USERS if u != u2]), _ip(rng, p2)))
        answer = f"{prefix}.0/24"
        q = (
            "An attacker rotated source addresses inside one /24 network. Treat all IPs in the same /24 as one "
            f"source. Find the /24 with at least {threshold} failed passwords for one user within any {window}-minute "
            f"span, followed within {window} minutes of its last failure by an accepted login for that same user from "
            "the same /24. Answer in CIDR form, like 198.51.100.0/24."
        )
        budget = 12
    events.sort(key=lambda e: e[0])
    lines = []
    pid = rng.randint(1000, 9000)
    host = rng.choice(["web01", "bastion", "db-2", "ci-runner"])
    for t, ok, user, ip in events:
        pid += rng.randint(1, 40)
        stamp = t.strftime("%b %d %H:%M:%S").replace(" 0", "  ", 1) if t.day < 10 else t.strftime("%b %d %H:%M:%S")
        port = rng.randint(30000, 65000)
        if ok:
            lines.append(f"{stamp} {host} sshd[{pid}]: Accepted password for {user} from {ip} port {port} ssh2")
        else:
            inv = "" if user in USERS[:8] else "invalid user "
            lines.append(f"{stamp} {host} sshd[{pid}]: Failed password for {inv}{user} from {ip} port {port} ssh2")
        if rng.random() < 0.15:
            pid += 1
            lines.append(f"{stamp} {host} CRON[{pid}]: pam_unix(cron:session): session opened for user root by (uid=0)")
    files = {"auth.log": "\n".join(lines) + "\n"}
    return Built(
        question=q + " The log is auth.log.",
        files=files,
        check=lambda a, answer=answer: same_text(a, answer),
        answer=answer,
        answer_hint="a string",
        budget=budget,
        wrong=[_ip(rng)],
    )
