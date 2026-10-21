"""Cybersecurity v4: forensics and audit tasks with a file deliverable."""
import base64
import codecs
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .base import Built
from .filetask import graded, parse_json

DOMAIN = "cybersecurity"


def _ip(rng):
    return f"{rng.choice([23, 45, 61, 77, 89, 103, 141, 176, 185, 193, 203, 212])}.{rng.randint(1, 254)}.{rng.randint(1, 254)}.{rng.randint(2, 250)}"


# --------------------------------------------------------------------------- web log forensics
UAS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
       "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
       "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
       "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"]
PAGES = ["/", "/index.html", "/about", "/products", "/products/42", "/cart", "/static/app.js", "/static/site.css",
         "/blog/release-notes", "/search?q=boots", "/api/v1/items?page=2", "/contact", "/favicon.ico"]
SQLI = ["/products?id=1'%20OR%20'1'='1", "/search?q=x'%20UNION%20SELECT%20username,password%20FROM%20users--",
        "/api/v1/items?id=1;DROP%20TABLE%20items--", "/products?id=1%20AND%20SLEEP(5)",
        "/search?q=%27%20or%201%3D1--", "/login?user=admin'--", "/products?id=-1%20UNION%20ALL%20SELECT%20NULL,version()"]
SCAN = ["/wp-login.php", "/.env", "/phpmyadmin/", "/admin/config.php", "/.git/config", "/server-status", "/backup.zip",
        "/wp-admin/install.php", "/cgi-bin/test.cgi", "/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php"]


class WebForensics:
    NAME = "web-forensics"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        tzh = rng.choice([-5, -4, 1, 2, 3, 8, 0]) if level == 2 else 0
        tz = timezone(timedelta(hours=tzh))
        start = datetime(2026, rng.randint(1, 9), rng.randint(1, 27), rng.randint(0, 20), 0, tzinfo=tz)
        span = 4 * 3600
        ev = []  # (t, ip, method, path, status, size, ua)
        for _ in range(rng.randint(140, 220)):
            ev.append((start + timedelta(seconds=rng.randint(0, span)), _ip(rng), "GET", rng.choice(PAGES),
                       rng.choice([200] * 12 + [304, 404]), rng.randint(200, 40000), rng.choice(UAS)))
        attacker = _ip(rng)
        a0 = start + timedelta(seconds=rng.randint(600, span - 2400))
        t = a0
        att = []
        if level == 1:
            # scanner: probes many paths, nearly all 404
            for p in rng.sample(SCAN, rng.randint(7, 10)) + rng.sample(SCAN, 4):
                t += timedelta(seconds=rng.randint(1, 20))
                att.append((t, attacker, "GET", p, 200 if p == "/.env" and rng.random() < 0.5 else 404,
                            rng.randint(150, 600), "python-requests/2.31"))
            # decoy: a busy but legit crawler with 200s
            bot = _ip(rng)
            for _ in range(len(att) + rng.randint(5, 15)):
                ev.append((start + timedelta(seconds=rng.randint(0, span)), bot, "GET", rng.choice(PAGES), 200,
                           rng.randint(300, 9000), "Googlebot/2.1 (+http://www.google.com/bot.html)"))
            # decoy: one 404 each from a few IPs
            for _ in range(4):
                ev.append((start + timedelta(seconds=rng.randint(0, span)), _ip(rng), "GET", rng.choice(SCAN), 404, 180, rng.choice(UAS)))
        else:
            for p in rng.sample(SQLI, rng.randint(4, 6)):
                t += timedelta(seconds=rng.randint(5, 90))
                att.append((t, attacker, "GET", p, rng.choice([200, 500, 403, 200]), rng.randint(150, 9000), rng.choice(UAS)))
            # attacker also browses normally (should count in requests but not in the payload list)
            for _ in range(rng.randint(3, 6)):
                t += timedelta(seconds=rng.randint(5, 120))
                att.append((t, attacker, "GET", rng.choice(PAGES), 200, rng.randint(200, 9000), rng.choice(UAS)))
            if not any(e[4] == 200 and e[3] in SQLI for e in att):
                e = att[0]
                att[0] = (e[0], e[1], e[2], e[3], 200, e[5], e[6])
            # decoy: a scanner with many 404s but no injection
            sc = _ip(rng)
            t2 = start + timedelta(seconds=rng.randint(0, span - 600))
            for p in rng.sample(SCAN, 9):
                t2 += timedelta(seconds=rng.randint(1, 15))
                ev.append((t2, sc, "GET", p, 404, 170, "Nikto/2.5.0"))
            # decoy: a benign search with an apostrophe
            ev.append((start + timedelta(seconds=rng.randint(0, span)), _ip(rng), "GET", "/search?q=o'neill%20boots", 200, 5120, rng.choice(UAS)))
            # attacker's earliest line arrives late in the file (log merged from two servers)
        ev += att
        ev.sort(key=lambda e: e[0])
        if level == 2:
            # merged log: shuffle blocks so the file is not in time order
            cut = rng.randint(len(ev) // 3, 2 * len(ev) // 3)
            ev = ev[cut:] + ev[:cut]
        lines = []
        for t, ip, m, p, st, sz, ua in ev:
            stamp = t.strftime("%d/%b/%Y:%H:%M:%S %z")
            lines.append(f'{ip} - - [{stamp}] "{m} {p} HTTP/1.1" {st} {sz} "-" "{ua}"')
        files = {"access.log": "\n".join(lines) + "\n"}
        ts = sorted(e[0] for e in att)
        to_utc = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if level == 1:
            q = ("access.log is an nginx combined log. One client is running a vulnerability scanner (it requests many "
                 "different sensitive paths and almost all of them return 404). Write output/incident.json with keys "
                 "attacker_ip, first_seen and last_seen (that client's first and last request, ISO 8601 UTC like "
                 "2026-03-01T14:05:09Z), request_count (all requests from that IP) and paths_200 (sorted list of the "
                 "paths that returned 200 to it).")
            ok_paths = sorted({e[3] for e in att if e[4] == 200})
        else:
            q = ("access.log is a merged nginx combined log (lines are NOT in time order; timestamps carry the server's "
                 "UTC offset). Exactly one client attempted SQL injection (UNION SELECT, tautologies like ' OR 1=1, "
                 "stacked queries, SLEEP, comment terminators). Write output/incident.json with keys attacker_ip, "
                 "first_seen and last_seen (that client's first and last request of any kind, ISO 8601 UTC like "
                 "2026-03-01T14:05:09Z), request_count (all requests from that IP), and paths_200: the sorted list of that "
                 "client's injection request paths (exactly as logged, query string included) that returned 200.")
            ok_paths = sorted({e[3] for e in att if e[4] == 200 and e[3] in SQLI})
        truth = {"attacker_ip": attacker, "first_seen": to_utc(ts[0]), "last_seen": to_utc(ts[-1]),
                 "request_count": len(att), "paths_200": ok_paths}
        answer = json.dumps(truth)

        def check(text, truth=truth):
            got = parse_json(text)
            if not isinstance(got, dict):
                return False
            for k in ("attacker_ip", "first_seen", "last_seen"):
                g = str(got.get(k, "")).strip()
                if k != "attacker_ip":
                    g = g.replace("+00:00", "Z")
                if g != truth[k]:
                    return False
            rc = got.get("request_count")
            if isinstance(rc, bool) or rc != truth["request_count"]:
                return False
            p = got.get("paths_200")
            return isinstance(p, list) and sorted(map(str, p)) == truth["paths_200"]

        local = dict(truth)
        local["first_seen"] = ts[0].strftime("%Y-%m-%dT%H:%M:%SZ")
        w2 = dict(truth)
        w2["request_count"] = truth["request_count"] + 1
        wrong = [json.dumps(local), json.dumps(w2), json.dumps({**truth, "attacker_ip": _ip(rng)})]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/incident.json", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/incident.json")


# --------------------------------------------------------------------------- decoding
WORDS = ["harbor", "maple", "orbit", "falcon", "cobalt", "ember", "violet", "quartz", "sierra", "tundra", "nectar",
         "pixel", "lumen", "zephyr", "garnet", "willow", "cipher", "atlas", "bramble", "canyon", "delta", "summit"]


def _xor(data, key):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


class DecodeChain:
    NAME = "decode-chain"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        key = bytes(rng.randrange(1, 256) for _ in range(rng.randint(3, 6)))
        n = 5 if level == 1 else 6
        plains, blobs = {}, []
        layers_all = ["base64", "hex", "rot13", "url", "xor"]
        for i in range(n):
            pt = "flag{" + "-".join(rng.sample(WORDS, 3)) + f"-{rng.randint(10, 9999)}" + "}"
            if level == 1:
                layers = [layers_all[i % 5]]
            else:
                layers = rng.sample(["base64", "hex", "rot13", "xor", "url"], rng.randint(2, 3))
                if "xor" in layers and layers[-1] != "xor" and layers.index("xor") == len(layers) - 1:
                    pass
            data = pt.encode()
            for lay in layers:
                if lay == "base64":
                    data = base64.b64encode(data)
                elif lay == "hex":
                    data = data.hex().encode()
                elif lay == "rot13":
                    data = codecs.encode(data.decode("latin-1"), "rot13").encode("latin-1")
                elif lay == "url":
                    data = "".join(f"%{b:02X}" for b in data).encode()
                elif lay == "xor":
                    data = _xor(data, key).hex().encode()
            bid = f"B{i + 1}"
            plains[bid] = pt
            blobs.append((bid, layers, data.decode("latin-1")))
        # hash cracking against a wordlist
        hashes = {}
        wl = sorted(set(rng.sample(WORDS, 14) + [f"{w}{rng.randint(1, 99)}" for w in rng.sample(WORDS, 6)]))
        algos = ["md5", "sha1", "sha256"] if level == 1 else ["md5", "sha1", "sha256", "sha512"]
        for j, alg in enumerate(rng.sample(algos, 2 if level == 1 else 3)):
            w = rng.choice(wl)
            salt = ""
            if level == 2 and j == 0:
                salt = f"{rng.randint(1000, 9999)}"
            hid = f"H{j + 1}"
            hashes[hid] = (alg, w, salt, hashlib.new(alg, (salt + w).encode()).hexdigest())
        lines = ["# Recovered artefacts. Each blob line: id<TAB>encoded data"]
        for bid, layers, data in blobs:
            hint = ""
            if level == 1:
                hint = f"\t# {layers[0]}" + (" (repeating-key XOR, shown as hex)" if layers[0] == "xor" else "")
            lines.append(f"{bid}\t{data}{hint}")
        lines.append("# Password hashes (unsalted unless a salt is given; salted = hash(salt + password)): id<TAB>hash<TAB>salt")
        for hid, (alg, w, salt, h) in hashes.items():
            lines.append(f"{hid}\t{h}\t{salt or '-'}")
        files = {"artefacts.txt": "\n".join(lines) + "\n", "wordlist.txt": "\n".join(wl) + "\n",
                 "notes.txt": f"XOR key recovered from the implant config (hex): {key.hex()}\n"
                              "XOR'd data is always stored as lowercase hex of the XOR output.\n"
                              + ("" if level == 1 else
                                 "Blobs can be wrapped in 2 or 3 layers of: base64, hex, rot13, URL percent-encoding, "
                                 "XOR (key above). Peel layers until you reach the plaintext, which always looks like "
                                 "flag{lowercase-words-and-a-number}.\n")}
        q = ("Decode every blob in artefacts.txt (notes.txt has the key) and crack every hash against wordlist.txt. "
             'Write output/decoded.json as {"blobs": {"B1": "plaintext", ...}, "hashes": {"H1": {"algorithm": "md5", '
             '"password": "..."}, ...}} (algorithm one of md5, sha1, sha256, sha512).')
        truth = {"blobs": plains, "hashes": {h: {"algorithm": a, "password": w} for h, (a, w, s, _) in hashes.items()}}
        answer = json.dumps(truth)

        def check(text, truth=truth):
            got = parse_json(text)
            if not isinstance(got, dict) or not isinstance(got.get("blobs"), dict) or not isinstance(got.get("hashes"), dict):
                return False
            if {k: str(v) for k, v in got["blobs"].items()} != truth["blobs"]:
                return False
            gh = got["hashes"]
            if set(gh) != set(truth["hashes"]):
                return False
            for h, v in truth["hashes"].items():
                g = gh[h]
                if not isinstance(g, dict) or str(g.get("algorithm", "")).lower().replace("-", "") != v["algorithm"] or g.get("password") != v["password"]:
                    return False
            return True

        w1 = json.loads(answer)
        w1["blobs"]["B1"] = w1["blobs"]["B1"].upper()
        w2 = json.loads(answer)
        first = next(iter(w2["hashes"]))
        w2["hashes"][first]["algorithm"] = "sha1" if w2["hashes"][first]["algorithm"] != "sha1" else "md5"
        wrong = [json.dumps(w1), json.dumps(w2)]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/decoded.json", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/decoded.json")


# --------------------------------------------------------------------------- sshd config audit
# rule id, keyword, default, predicate(value)->compliant, policy text
RULES = [
    ("SSH-01", "permitrootlogin", "prohibit-password", lambda v: v == "no", "PermitRootLogin must be no"),
    ("SSH-02", "passwordauthentication", "yes", lambda v: v == "no", "PasswordAuthentication must be no"),
    ("SSH-03", "permitemptypasswords", "no", lambda v: v == "no", "PermitEmptyPasswords must be no"),
    ("SSH-04", "maxauthtries", "6", lambda v: v.isdigit() and int(v) <= 4, "MaxAuthTries must be 4 or less"),
    ("SSH-05", "x11forwarding", "no", lambda v: v == "no", "X11Forwarding must be no"),
    ("SSH-06", "logingracetime", "120", lambda v: _secs(v) is not None and 0 < _secs(v) <= 60,
     "LoginGraceTime must be between 1 and 60 seconds (0 means unlimited and fails)"),
    ("SSH-07", "ciphers", "chacha20-poly1305@openssh.com,aes128-ctr,aes192-ctr,aes256-ctr,aes128-gcm@openssh.com,aes256-gcm@openssh.com",
     lambda v: not any(("cbc" in c or "arcfour" in c or "3des" in c) for c in v.split(",")),
     "Ciphers must not include any CBC, arcfour or 3DES cipher"),
    ("SSH-08", "allowtcpforwarding", "yes", lambda v: v == "no", "AllowTcpForwarding must be no"),
    ("SSH-09", "clientaliveinterval", "0", lambda v: v.isdigit() and 0 < int(v) <= 300,
     "ClientAliveInterval must be between 1 and 300"),
    ("SSH-10", "usepam", "no", lambda v: v == "yes", "UsePAM must be yes"),
    ("SSH-11", "loglevel", "info", lambda v: v in ("verbose", "info"), "LogLevel must be INFO or VERBOSE"),
    ("SSH-12", "hostbasedauthentication", "no", lambda v: v == "no", "HostbasedAuthentication must be no"),
]
CANON = {"permitrootlogin": "PermitRootLogin", "passwordauthentication": "PasswordAuthentication",
         "permitemptypasswords": "PermitEmptyPasswords", "maxauthtries": "MaxAuthTries", "x11forwarding": "X11Forwarding",
         "logingracetime": "LoginGraceTime", "ciphers": "Ciphers", "allowtcpforwarding": "AllowTcpForwarding",
         "clientaliveinterval": "ClientAliveInterval", "usepam": "UsePAM", "loglevel": "LogLevel",
         "hostbasedauthentication": "HostbasedAuthentication"}
GOOD = {"permitrootlogin": ["no"], "passwordauthentication": ["no"], "permitemptypasswords": ["no"],
        "maxauthtries": ["3", "4", "2"], "x11forwarding": ["no"], "logingracetime": ["30", "45s", "1m", "60"],
        "ciphers": ["chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes256-ctr"], "allowtcpforwarding": ["no"],
        "clientaliveinterval": ["300", "120"], "usepam": ["yes"], "loglevel": ["VERBOSE", "INFO"],
        "hostbasedauthentication": ["no"]}
BAD = {"permitrootlogin": ["yes", "prohibit-password", "without-password"], "passwordauthentication": ["yes"],
       "permitemptypasswords": ["yes"], "maxauthtries": ["6", "10", "5"], "x11forwarding": ["yes"],
       "logingracetime": ["2m", "0", "90", "120"], "ciphers": ["aes128-ctr,aes256-cbc", "3des-cbc,aes128-ctr", "arcfour256,aes256-ctr"],
       "allowtcpforwarding": ["yes", "all"], "clientaliveinterval": ["0", "900"], "usepam": ["no"],
       "loglevel": ["QUIET", "ERROR"], "hostbasedauthentication": ["yes"]}


def _secs(v):
    v = v.lower()
    total, numb = 0, ""
    if not v:
        return None
    for ch in v:
        if ch.isdigit():
            numb += ch
        elif ch in "smhdw" and numb:
            total += int(numb) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[ch]
            numb = ""
        else:
            return None
    if numb:
        total += int(numb)
    return total


class SshdAudit:
    NAME = "sshd-audit"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        rules = rng.sample(RULES, 8 if level == 1 else 10)
        ids = {r[0] for r in rules}
        blocks = [[x] for x in ["Port 22", "AddressFamily any", "ListenAddress 0.0.0.0",
                                "HostKey /etc/ssh/ssh_host_ed25519_key", "AuthorizedKeysFile .ssh/authorized_keys",
                                "Subsystem sftp /usr/lib/openssh/sftp-server", "AcceptEnv LANG LC_*"]]
        dups = []
        effective = {}
        decoy_effective_good = []
        for rid, kw, default, ok, _ in rules:
            mode = rng.random()
            if level == 2 and mode < 0.15:
                effective[kw] = default  # absent: default applies
                continue
            if level == 2 and mode < 0.35:
                # duplicate keyword: the FIRST occurrence wins in sshd
                v1 = rng.choice(GOOD[kw] + BAD[kw])
                v2 = rng.choice(GOOD[kw] if not ok(v1.lower()) else BAD[kw])
                blocks.append([f"{CANON[kw] if rng.random() < 0.7 else kw.upper()} {v1}"])
                dups.append(["# later override added by ops ticket", f"{CANON[kw]} {v2}"])
                effective[kw] = v1.lower()
                continue
            v = rng.choice(GOOD[kw] if rng.random() < 0.5 else BAD[kw])
            key = CANON[kw] if level == 1 or rng.random() < 0.7 else rng.choice([kw, kw.upper()])
            sep = " " if level == 1 or rng.random() < 0.7 else rng.choice(["\t", "  ", " = ", "="])
            blk = []
            if level == 1 and rng.random() < 0.3:
                blk.append(f"#{CANON[kw]} {rng.choice(BAD[kw] + GOOD[kw])}")
            blk.append(f"{key}{sep}{v}")
            blocks.append(blk)
            effective[kw] = v.lower()
        rng.shuffle(blocks)
        # overrides go after every first occurrence, so the first value really is first
        lines = ["# sshd_config managed by config-mgmt; local edits below"] + [x for b in blocks for x in b] + [x for b in dups for x in b]
        tail = []
        if level == 2:
            kw = rng.choice([r[1] for r in rules])
            tail = ["", "Match User backup", f"    {CANON[kw]} {rng.choice(GOOD[kw] if not RULES_OK(kw, effective) else BAD[kw])}",
                    "    ForceCommand internal-sftp"]
        files = {"sshd_config": "\n".join(lines + tail) + "\n"}
        pol = ["# Hardening baseline (global settings)", ""]
        for rid, kw, default, ok, text in sorted(rules):
            pol.append(f"{rid}: {text}.")
        pol += ["", "Audit the effective global configuration: keywords are case-insensitive; a keyword absent from the "
                "file takes the OpenSSH default; settings inside Match blocks do not count for the global audit."]
        if level == 2:
            pol.append("Like sshd itself, when a keyword appears more than once outside Match blocks the FIRST value wins. "
                       "Keyword and value may be separated by whitespace or '='.")
            pol.append("OpenSSH defaults: " + "; ".join(f"{CANON[kw]} {d}" for _, kw, d, _, _ in sorted(rules)) + ".")
        files["baseline.md"] = "\n".join(pol) + "\n"
        failing = sorted(rid for rid, kw, d, ok, _ in rules if not ok(effective.get(kw, d).lower()))
        q = ("Audit sshd_config against baseline.md. Write output/findings.json as "
             '{"failing": ["SSH-02", ...]} listing the ids of every failing rule, sorted.')
        answer = json.dumps({"failing": failing})

        def check(text, failing=failing):
            got = parse_json(text)
            if isinstance(got, dict):
                got = got.get("failing")
            return isinstance(got, list) and sorted(set(map(str, got))) == failing and len(got) == len(failing)

        wrong = [json.dumps({"failing": failing[1:]}), json.dumps({"failing": sorted(ids - set(failing))})]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/findings.json", budget=14 if level == 1 else 18,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/findings.json")


def RULES_OK(kw, effective):
    for rid, k, d, ok, _ in RULES:
        if k == kw:
            return ok(effective.get(kw, d).lower())
    return True


# --------------------------------------------------------------------------- JWT inspection
def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _jwt(header, payload, key):
    h = _b64u(json.dumps(header, separators=(",", ":")).encode())
    p = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    if header.get("alg") == "none":
        return f"{h}.{p}."
    sig = hmac.new(key, f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64u(sig)}"


class JwtInspect:
    NAME = "jwt-inspect"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        now = int(datetime(2026, rng.randint(1, 12), rng.randint(1, 27), rng.randint(0, 23), tzinfo=timezone.utc).timestamp())
        iss = rng.choice(["https://auth.example.com", "https://sso.acme.test", "https://id.internal.test"])
        aud = rng.choice(["billing-api", "orders-api", "admin-portal"])
        keys = {f"k{i}": "".join(rng.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(24)) for i in range(1, 3 if level == 1 else 4)}
        reasons_l1 = ["ok", "bad_signature", "expired", "alg_none", "wrong_issuer"]
        reasons_l2 = reasons_l1 + ["not_yet_valid", "wrong_audience", "unknown_kid"]
        pool = reasons_l1 if level == 1 else reasons_l2
        n = 7 if level == 1 else 9
        want = pool + [rng.choice(pool) for _ in range(n - len(pool))]
        rng.shuffle(want)
        rows, truth = [], {}
        users = ["alice", "bob", "carol", "dmitri", "erin", "farah", "gus", "hana", "ivan", "jo"]
        for i, r in enumerate(want):
            kid = rng.choice(sorted(keys))
            sub = rng.choice(users)
            p = {"sub": sub, "iss": iss, "iat": now - rng.randint(600, 7200), "exp": now + rng.randint(300, 86400)}
            if level == 2:
                p["aud"] = aud if rng.random() < 0.5 else [aud, rng.choice(["mobile", "web"])]
                if rng.random() < 0.5:
                    p["nbf"] = now - rng.randint(0, 3600)
            h = {"alg": "HS256", "typ": "JWT"}
            if level == 2:
                h["kid"] = kid
            key = keys[kid].encode()
            if r == "expired":
                p["exp"] = now - rng.randint(1, 5000)
            elif r == "wrong_issuer":
                p["iss"] = iss.replace("https://", "https://evil-") if rng.random() < 0.5 else iss + ".attacker.test"
            elif r == "alg_none":
                h["alg"] = "none"
            elif r == "bad_signature":
                key = b"x" + key
            elif r == "not_yet_valid":
                p["nbf"] = now + rng.randint(60, 9000)
            elif r == "wrong_audience":
                p["aud"] = rng.choice(["mobile", "reporting-api", [rng.choice(["mobile", "web"])]])
            elif r == "unknown_kid":
                h["kid"] = f"k{len(keys) + rng.randint(1, 5)}"
            # stack a later-priority defect onto some tokens to test the order
            if level == 2 and r in ("bad_signature", "alg_none") and rng.random() < 0.6:
                p["exp"] = now - rng.randint(1, 5000)
            if level == 2 and r == "unknown_kid" and rng.random() < 0.6:
                p["iss"] = iss + ".attacker.test"
            tid = f"T{i + 1:02d}"
            rows.append(f"{tid} {_jwt(h, p, key)}")
            truth[tid] = {"valid": r == "ok", "reason": r, "sub": sub}
        order = (["alg_none", "bad_signature", "expired", "wrong_issuer"] if level == 1 else
                 ["alg_none", "unknown_kid", "bad_signature", "expired", "not_yet_valid", "wrong_issuer", "wrong_audience"])
        cfg = [f"now (unix seconds, UTC): {now}", f"expected issuer: {iss}"]
        if level == 2:
            cfg.append(f"expected audience: {aud} (aud may be a string or a list; it must contain this value)")
            cfg += [f"key {k}: {v}" for k, v in keys.items()]
            cfg.append("Each token's header names its key in kid. Signatures are HMAC-SHA256 over 'header.payload' "
                       "using the key string's UTF-8 bytes.")
        else:
            cfg.append(f"HMAC-SHA256 secret (UTF-8 bytes): {keys['k1']}")
            # level 1 uses only k1
        files = {"tokens.txt": "\n".join(rows) + "\n", "verifier.md": "\n".join(cfg + [
            "A token is rejected for the FIRST failing check in this order: " + ", ".join(order) + ".",
            "exp: rejected when now >= exp. nbf: rejected when now < nbf." if level == 2 else "exp: rejected when now >= exp.",
            "Reason codes: ok, " + ", ".join(order) + "."]) + "\n"}
        if level == 1:
            # rebuild with the single key for every token
            rows, truth = [], {}
            for i, r in enumerate(want):
                sub = rng.choice(users)
                p = {"sub": sub, "iss": iss, "iat": now - rng.randint(600, 7200), "exp": now + rng.randint(300, 86400)}
                h = {"alg": "HS256", "typ": "JWT"}
                key = keys["k1"].encode()
                if r == "expired":
                    p["exp"] = now - rng.randint(1, 5000)
                elif r == "wrong_issuer":
                    p["iss"] = iss + ".attacker.test"
                elif r == "alg_none":
                    h["alg"] = "none"
                elif r == "bad_signature":
                    key = b"x" + key
                tid = f"T{i + 1:02d}"
                rows.append(f"{tid} {_jwt(h, p, key)}")
                truth[tid] = {"valid": r == "ok", "reason": r, "sub": sub}
            files["tokens.txt"] = "\n".join(rows) + "\n"
        q = ("Inspect every JWT in tokens.txt using the rules in verifier.md. Write output/report.json mapping each token "
             'id to {"valid": true/false, "reason": "<code>", "sub": "<sub claim>"}.')
        answer = json.dumps(truth)

        def check(text, truth=truth):
            got = parse_json(text)
            if not isinstance(got, dict) or set(got) != set(truth):
                return False
            for k, v in truth.items():
                g = got[k]
                if not isinstance(g, dict) or g.get("valid") is not v["valid"] or str(g.get("reason", "")).lower() != v["reason"] or g.get("sub") != v["sub"]:
                    return False
            return True

        w = json.loads(answer)
        for k in w:
            if w[k]["reason"] == "bad_signature":
                w[k] = {"valid": True, "reason": "ok", "sub": w[k]["sub"]}
        wrong = [json.dumps(w), json.dumps({k: {"valid": True, "reason": "ok", "sub": v["sub"]} for k, v in truth.items()})]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/report.json", budget=16 if level == 1 else 20,
                     wrong=[x for x in wrong if not check(x)], deliverable="output/report.json")
