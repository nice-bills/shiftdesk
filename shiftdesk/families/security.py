"""Cybersecurity v3 families: firewall rule evaluation and vulnerability triage."""
import ipaddress
import json

from ..grading import exact_int, fields, same_list
from .base import Built

DOMAIN = "cybersecurity"


class FirewallAudit:
    NAME = "firewall-audit"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        nets = ["10.0.0.0/8", "10.1.0.0/16", "10.1.2.0/24", "192.168.0.0/16", "192.168.10.0/24",
                "172.16.0.0/12", "0.0.0.0/0", "10.2.0.0/16", "192.168.10.128/25"]
        ports = [(22, 22), (80, 80), (443, 443), (3306, 3306), (8000, 8999), (1, 1023), (5432, 5432), (53, 53)]
        rules = []
        for i in range(rng.randint(6, 9)):
            lo, hi = rng.choice(ports)
            rules.append({"id": f"R{i + 1}", "action": rng.choice(["allow", "deny"]),
                          "proto": rng.choice(["tcp", "tcp", "udp", "any"]),
                          "src": rng.choice(nets), "ports": (lo, hi)})
        change = None
        final = list(rules)
        if level == 2:
            kind = rng.choice(["remove", "insert"])
            if kind == "remove":
                r = rng.choice(rules)
                final = [x for x in rules if x is not r]
                change = f"CHG-{rng.randint(100, 999)}: rule {r['id']} was deleted from the live firewall."
            else:
                lo, hi = rng.choice(ports)
                nr = {"id": "R0", "action": rng.choice(["allow", "deny"]), "proto": "tcp",
                      "src": rng.choice(nets[:6]), "ports": (lo, hi)}
                final = [nr] + rules
                pr = f"{lo}" if lo == hi else f"{lo}-{hi}"
                change = (f"CHG-{rng.randint(100, 999)}: a new rule R0 was inserted at the top of the live firewall: "
                          f"{nr['action']} tcp from {nr['src']} to port {pr}.")

        def verdict(pkt, rl):
            ip = ipaddress.ip_address(pkt["src"])
            for r in rl:
                if r["proto"] != "any" and r["proto"] != pkt["proto"]:
                    continue
                if ip not in ipaddress.ip_network(r["src"]):
                    continue
                if not (r["ports"][0] <= pkt["port"] <= r["ports"][1]):
                    continue
                return r["action"] == "allow"
            return False

        pkts = []
        for j in range(rng.randint(10, 14)):
            src = rng.choice(["10.1.2.", "10.1.9.", "10.7.3.", "192.168.10.", "192.168.4.", "172.20.1.", "8.8.4."])
            src += str(rng.choice([5, 77, 130, 200]))
            pkts.append({"id": f"P{j + 1:02d}", "src": src, "proto": rng.choice(["tcp", "tcp", "udp"]),
                         "port": rng.choice([22, 53, 80, 443, 3306, 5432, 8080, 8443, 25])})
        allowed = [p["id"] for p in pkts if verdict(p, final)]
        old_allowed = [p["id"] for p in pkts if verdict(p, rules)]
        any_allowed = [p["id"] for p in pkts if any(verdict(p, [r]) for r in final if r["action"] == "allow")]
        if not allowed or len(allowed) == len(pkts) or (level == 2 and allowed == old_allowed) or any_allowed == allowed:
            return FirewallAudit.build(level, rng)

        def fmt(r):
            pr = f"{r['ports'][0]}" if r["ports"][0] == r["ports"][1] else f"{r['ports'][0]}-{r['ports'][1]}"
            return f"{r['id']} {r['action']} proto={r['proto']} src={r['src']} dport={pr}"
        ruleset = ["# Rules are evaluated top to bottom; the first match decides. No match: deny.",
                   "# proto=any matches tcp and udp."] + [fmt(r) for r in rules]
        files = {"rules.txt": "\n".join(ruleset) + "\n",
                 "packets.csv": "id,src_ip,proto,dst_port\n" + "".join(
                     f"{p['id']},{p['src']},{p['proto']},{p['port']}\n" for p in pkts)}
        if level == 2:
            files["change_log.txt"] = "Approved changes not yet reflected in rules.txt\n" + change + "\n"
        return Built(
            question=("Which packets in packets.csv does the live firewall allow?"
                      + (" Apply change_log.txt to rules.txt first." if level == 2 else "")),
            files=files,
            check=lambda a: fields(a, {"allowed": lambda v: same_list(v, allowed, case=True)}),
            answer={"allowed": sorted(allowed)},
            answer_hint='a JSON object {"allowed": ["P01", "P07"]} listing every allowed packet id',
            budget=8,
            wrong=[{"allowed": sorted(any_allowed)}] + ([{"allowed": sorted(old_allowed)}] if level == 2 else []),
        )


PKGS = ["openssl", "nginx", "log4j-core", "libxml2", "sudo", "zlib", "curl", "openssh"]


def _v(s):
    return tuple(int(x) for x in s.split("."))


class VulnTriage:
    NAME = "vuln-triage"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        pkgs = rng.sample(PKGS, 4)
        advisories = []
        for i, p in enumerate(pkgs[:3]):
            major = rng.randint(1, 3)
            lo = f"{major}.{rng.randint(0, 3)}.0"
            fixed = f"{major}.{rng.randint(9, 12)}.{rng.randint(0, 4)}"
            advisories.append({"id": f"CVE-2026-{rng.randint(10000, 49999)}", "package": p,
                               "affected": f">={lo}, <{fixed}", "lo": lo, "fixed": fixed,
                               "severity": rng.choice(["high", "critical", "medium"])})
        hosts = []
        for h in range(rng.randint(8, 12)):
            name = f"{rng.choice(['web', 'db', 'app', 'edge', 'ci'])}-{h + 1:02d}"
            for p in rng.sample(pkgs, rng.randint(2, 4)):
                adv = next((a for a in advisories if a["package"] == p), None)
                if adv and rng.random() < 0.75:
                    major = _v(adv["fixed"])[0]
                    ver = f"{major}.{rng.randint(0, 13)}.{rng.randint(0, 9)}"
                else:
                    ver = f"{rng.randint(1, 3)}.{rng.randint(0, 13)}.{rng.randint(0, 9)}"
                hosts.append((name, p, ver))
        backports = []
        if level == 2:
            vuln_rows = [r for r in hosts if any(a["package"] == r[1] and _v(a["lo"]) <= _v(r[2]) < _v(a["fixed"])
                                                 for a in advisories)]
            if len(vuln_rows) < 3:
                return VulnTriage.build(level, rng)
            for r in rng.sample(vuln_rows, 2):
                adv = next(a for a in advisories if a["package"] == r[1])
                backports.append((r[0], r[1], adv["id"]))
        bp = {(h, p) for h, p, _ in backports}
        affected = sorted({h for h, p, v in hosts for a in advisories
                           if a["package"] == p and _v(a["lo"]) <= _v(v) < _v(a["fixed"]) and (h, p) not in bp})
        # wrong: string comparison of versions
        str_aff = sorted({h for h, p, v in hosts for a in advisories
                          if a["package"] == p and a["lo"] <= v < a["fixed"] and (h, p) not in bp})
        nobp = sorted({h for h, p, v in hosts for a in advisories
                       if a["package"] == p and _v(a["lo"]) <= _v(v) < _v(a["fixed"])})
        if not affected or str_aff == affected or (level == 2 and nobp == affected):
            return VulnTriage.build(level, rng)
        inv = "host,package,version\n" + "".join(f"{h},{p},{v}\n" for h, p, v in hosts)
        adv = [{"id": a["id"], "package": a["package"], "affected_versions": a["affected"],
                "severity": a["severity"]} for a in advisories]
        files = {"inventory.csv": inv, "advisories.json": json.dumps(adv, indent=1) + "\n"}
        if level == 2:
            files["vendor_notes.txt"] = ("Vendor backport notices: these hosts run a distro build with the fix "
                                         "backported, so they are NOT affected despite the version number.\n" +
                                         "".join(f"- {h}: {p} ({cid})\n" for h, p, cid in backports))
        return Built(
            question=("Versions are semantic (major.minor.patch, compared numerically). Which hosts run at least one "
                      "package version covered by an advisory? Also give how many hosts that is."),
            files=files,
            check=lambda a: fields(a, {"hosts": lambda v: same_list(v, affected, case=True),
                                       "count": lambda v: exact_int(v, len(affected))}),
            answer={"hosts": affected, "count": len(affected)},
            answer_hint='a JSON object {"hosts": ["app-03", "web-01"], "count": 2}',
            budget=8,
            wrong=[{"hosts": str_aff, "count": len(str_aff)}] + ([{"hosts": nobp, "count": len(nobp)}] if level == 2 else []),
        )
