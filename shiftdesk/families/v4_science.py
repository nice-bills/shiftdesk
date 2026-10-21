"""Natural science v4: file-deliverable lab tasks (assay reduction, peak picking, dilution plans, PK fits)."""
import json
import math
from datetime import datetime, timedelta

from .base import Built
from .filetask import graded, keyed, near, parse_csv, parse_json, rows_to_csv

DOMAIN = "natural-science"


def _ols(xs, ys):
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    m = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return m, (sy - m * sx) / n


# --------------------------------------------------------------------------- assay reduction
UNITS = {"mg/L": 1.0, "ug/mL": 1.0, "ng/uL": 1.0, "g/L": 1000.0, "ug/L": 0.001}


class AssayReduction:
    NAME = "assay-reduction"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        analyte = rng.choice(["nitrate", "phosphate", "caffeine", "protein", "glucose", "riboflavin"])
        slope = rng.uniform(40, 400)
        blank = rng.uniform(80, 160)
        top = rng.choice([5.0, 10.0, 20.0, 50.0])
        stds = [0.0] + [round(top * f, 4) for f in (0.05, 0.1, 0.2, 0.5, 1.0)]
        rows = []  # well, type, id, conc_text, unit, dilution, signal
        wells = iter(f"{r}{c}" for r in "ABCDEFGH" for c in range(1, 13))
        reps = 3 if level == 2 else 1
        flags = []

        def sig(c, err=1.0):
            return round((blank + slope * c) * rng.uniform(0.995, 1.005) * err, 1)

        for _ in range(3):
            rows.append([next(wells), "blank", "BLK", "", "", "", sig(0)])
        for i, c in enumerate(stds):
            unit = rng.choice(list(UNITS)) if level == 2 else "mg/L"
            val = c / UNITS[unit]
            rows.append([next(wells), "std", f"STD{i}", f"{val:g}", unit, "", sig(c)])
        n_s = rng.randint(4, 6)
        samples = []
        for j in range(n_s):
            sid = f"S{j + 1:02d}"
            dil = rng.choice([1, 2, 5, 10, 20])
            c_meas = rng.uniform(0.08, 0.9) * top
            samples.append(sid)
            for _ in range(reps):
                rows.append([next(wells), "sample", sid, "", "", str(dil), sig(c_meas)])
        above = None
        if level == 2:
            above = rng.choice(samples)
            for r in rows:
                if r[2] == above:
                    r[6] = round((blank + slope * top * rng.uniform(1.25, 1.6)) * rng.uniform(0.995, 1.005), 1)
            # gross errors in flagged wells
            std_rows = [r for r in rows if r[1] == "std" and r[2] != "STD0"]
            s_rows = [r for r in rows if r[1] == "sample" and r[2] != above]
            for r, why in ((rng.choice(std_rows), "bubble in well"),
                           (rng.choice(s_rows), "pipetting error"),
                           (rng.choice([r for r in rows if r[1] == "blank"]), "edge evaporation")):
                r[6] = round(r[6] * rng.uniform(1.3, 1.6), 1)
                flags.append((r[0], why))
        rng.shuffle(rows)
        flagged = {w for w, _ in flags}

        # reference
        def ref(use_flags=True, use_dil=True, use_blank=True):
            ok = [r for r in rows if not (use_flags and r[0] in flagged)]
            bl = [r[6] for r in ok if r[1] == "blank"]
            b0 = sum(bl) / len(bl) if use_blank else 0.0
            st = [(float(r[3]) * UNITS[r[4]], r[6] - b0) for r in ok if r[1] == "std"]
            m, b = _ols([x for x, _ in st], [y for _, y in st])
            ytop = max(y for x, y in st if x == max(xx for xx, _ in st))
            out = {}
            for sid in samples:
                ws = [r for r in ok if r[2] == sid]
                y = sum(r[6] for r in ws) / len(ws) - b0
                dil = float(ws[0][5]) if use_dil else 1.0
                if level == 2 and y > ytop:
                    out[sid] = (None, "above_range")
                else:
                    out[sid] = ((y - b) / m * dil, "ok")
            return out

        truth = ref()
        header = ["well", "type", "id", "conc", "unit", "dilution", "signal"]
        files = {"plate.csv": rows_to_csv(header, rows)}
        proto = [f"# {analyte.title()} plate assay: data reduction SOP", "",
                 "1. Average the blank wells and subtract that mean from every standard and sample signal.",
                 "2. Fit a straight line (ordinary least squares, with intercept) of blank-corrected signal against "
                 "standard concentration in mg/L.",
                 "3. Sample concentration in the well = (corrected signal - intercept) / slope; multiply by the "
                 "sample's dilution factor to get the original concentration."]
        if level == 2:
            proto += ["4. Standards may be recorded in different units; convert every standard to mg/L first "
                      "(1 g/L = 1000 mg/L; 1 ug/mL = 1 ng/uL = 1 mg/L; 1 ug/L = 0.001 mg/L).",
                      "5. Wells listed in qc_flags.txt failed QC: drop them everywhere (blanks, standards, samples).",
                      "6. Samples are run in replicate wells: average the remaining replicates' signals before step 3.",
                      "7. A sample whose mean corrected signal is above the corrected signal of the highest standard is "
                      "out of range: report status above_range and leave its concentration empty. Others get status ok."]
            files["qc_flags.txt"] = "well,reason\n" + "".join(f"{w},{why}\n" for w, why in flags)
        files["protocol.md"] = "\n".join(proto) + "\n"
        if level == 1:
            q = (f"Reduce the {analyte} assay in plate.csv following protocol.md and write output/results.csv "
                 "with columns sample_id,conc_mg_per_L (one row per sample, original undiluted concentration).")
            out_rows = [[s, f"{truth[s][0]:.4f}"] for s in samples]
            answer = rows_to_csv(["sample_id", "conc_mg_per_L"], out_rows)
        else:
            q = (f"Reduce the {analyte} assay in plate.csv following every step of protocol.md and write "
                 "output/results.csv with columns sample_id,conc_mg_per_L,status (one row per sample).")
            out_rows = [[s, "" if truth[s][0] is None else f"{truth[s][0]:.4f}", truth[s][1]] for s in samples]
            answer = rows_to_csv(["sample_id", "conc_mg_per_L", "status"], out_rows)

        def check(text, truth=truth, level=level):
            rows_ = parse_csv(text)
            got = keyed(rows_, "sample_id")
            if got is None or set(got) != set(truth):
                return False
            for sid, (c, st) in truth.items():
                r = got[sid]
                if level == 2 and r.get("status", "").lower() != st:
                    return False
                if c is None:
                    if r.get("conc_mg_per_l", "").strip() not in ("", "nan", "na", "null"):
                        return False
                elif not near(r.get("conc_mg_per_l"), c, rel=0.01, abs_tol=1e-4):
                    return False
            return True

        wrong = []
        for kw in ({"use_dil": False}, {"use_blank": False}) + (({"use_flags": False},) if level == 2 else ()):
            alt = ref(**kw)
            if level == 1:
                wrong.append(rows_to_csv(["sample_id", "conc_mg_per_L"], [[s, f"{alt[s][0]:.4f}"] for s in samples]))
            else:
                wrong.append(rows_to_csv(["sample_id", "conc_mg_per_L", "status"],
                                         [[s, "" if alt[s][0] is None else f"{alt[s][0]:.4f}", alt[s][1]] for s in samples]))
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/results.csv", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/results.csv")


# --------------------------------------------------------------------------- peak picking
def _pick(xs, ys, thr, win):
    peaks = []
    n = len(xs)
    j0 = 0
    for i in range(n):
        if ys[i] < thr:
            continue
        lo = xs[i] - win - 1e-9
        hi = xs[i] + win + 1e-9
        best = True
        k = i - 1
        while k >= 0 and xs[k] >= lo:
            if ys[k] >= ys[i]:
                best = False
                break
            k -= 1
        if best:
            k = i + 1
            while k < n and xs[k] <= hi:
                if ys[k] >= ys[i]:
                    best = False
                    break
                k += 1
        if best:
            peaks.append((xs[i], ys[i]))
    return peaks


def _despike(ys, jump):
    out = list(ys)
    for i in range(1, len(ys) - 1):
        if ys[i] - ys[i - 1] > jump and ys[i] - ys[i + 1] > jump:
            out[i] = (ys[i - 1] + ys[i + 1]) / 2
    return out


class PeakPicking:
    NAME = "peak-picking"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        for _ in range(50):
            built = PeakPicking._try(level, rng)
            if built is not None:
                return built
        raise RuntimeError("peak-picking: no clean instance")

    @staticmethod
    def _try(level, rng):
        if level == 1:
            xs = [400 + 2 * i for i in range(1800)]
            lo, hi, sep, smin, smax, thr, win, unit = 500, 3900, 100, 5, 15, 30.0, 30, "cm-1"
            key = "position_cm1"
        else:
            xs = [400 + 0.5 * i for i in range(800)]
            lo, hi, sep, smin, smax, thr, win, unit = 430, 770, 40, 3, 6, 40.0, 15, "nm"
            key = "position_nm"
        k = rng.randint(3, 6) if level == 1 else rng.randint(3, 5)
        centers = []
        while len(centers) < k:
            c = rng.uniform(lo, hi)
            if all(abs(c - d) >= sep for d in centers):
                centers.append(c)
        gs = [(c, rng.uniform(60 if level == 1 else 80, 1000 if level == 1 else 900), rng.uniform(smin, smax)) for c in centers]
        # one small sub-threshold peak
        for _ in range(100):
            c = rng.uniform(lo, hi)
            if all(abs(c - d) >= sep for d in centers):
                small = (c, rng.uniform(10, thr * 0.6), rng.uniform(smin, smax))
                break
        else:
            return None
        allg = gs + [small]
        base_a, base_b = (rng.uniform(20, 80), rng.uniform(-0.1, 0.1)) if level == 2 else (0.0, 0.0)
        ys = []
        for x in xs:
            y = base_a + base_b * (x - 400) + sum(h * math.exp(-0.5 * ((x - c) / s) ** 2) for c, h, s in allg)
            ys.append(round(y + rng.uniform(-1.5, 1.5), 2))
        windows = []
        spikes = []
        if level == 2:
            far = lambda x, d: all(abs(x - c) >= d for c, _, _ in allg)
            cand = [i for i in range(2, len(xs) - 2) if far(xs[i], 30)]
            rng.shuffle(cand)
            for i in cand:
                if len(spikes) >= rng.randint(2, 3):
                    break
                if all(abs(xs[i] - xs[j]) > 20 for j in spikes):
                    spikes.append(i)
            if len(spikes) < 2:
                return None
            for i in spikes:
                ys[i] = round(ys[i] + rng.uniform(150, 500), 2)
            starts = [s for s in range(400, 786, 5) if all(far(x, 0) for x in (s,)) and
                      all(abs(x - c) >= 5 * sg for c, _, sg in allg for x in (s, s + 12)) and
                      all(not (s - 1 <= xs[i] <= s + 13) for i in spikes)]
            rng.shuffle(starts)
            for s in starts:
                if len(windows) >= 3:
                    break
                if all(abs(s - w) >= 60 for w, _ in windows):
                    windows.append((s, s + 12))
            if len(windows) < 3:
                return None
            windows.sort()
        # reference
        if level == 2:
            bx = [x for x in xs if any(a <= x <= b for a, b in windows)]
            by = [y for x, y in zip(xs, ys) if any(a <= x <= b for a, b in windows)]
            m, b = _ols(bx, by)
            corr = [y - (m * x + b) for x, y in zip(xs, ys)]
            corr = _despike(corr, 60.0)
        else:
            corr = list(ys)
        peaks = _pick(xs, corr, thr, win)
        expect = sorted(c for c, h, s in gs)
        if len(peaks) != len(expect) or any(abs(p[0] - c) > 3 * (xs[1] - xs[0]) for p, c in zip(peaks, expect)):
            return None
        # no detection ambiguity: every peak height is well clear of the threshold
        if any(p[1] < thr * 1.4 for p in peaks):
            return None
        col = "wavenumber_cm1" if level == 1 else "wavelength_nm"
        files = {"spectrum.csv": f"{col},intensity\n" + "".join(f"{x:g},{y:.2f}\n" for x, y in zip(xs, ys))}
        rules = [f"# Peak table SOP ({'FTIR' if level == 1 else 'UV-Vis emission'})", ""]
        step = 1
        if level == 2:
            rules.append(f"{step}. Baseline: fit one straight line (least squares) to every point whose wavelength lies "
                         "inside these peak-free windows (inclusive), and subtract it from the whole spectrum: "
                         + ", ".join(f"{a}-{b} nm" for a, b in windows) + ".")
            step += 1
            rules.append(f"{step}. Cosmic rays: after baseline subtraction, any single point that is more than 60 counts "
                         "above BOTH of its neighbours is a cosmic-ray hit; replace it with the mean of its two neighbours "
                         "(use the neighbours' values before any replacement).")
            step += 1
        rules.append(f"{step}. A peak is a point whose intensity{' (corrected)' if level == 2 else ''} is at least "
                     f"{thr:g} and strictly greater than every other point within +/-{win} {unit} of it.")
        rules.append(f"{step + 1}. Report each peak's position (the x value of that point) and its height (that point's "
                     f"{'corrected ' if level == 2 else ''}intensity), sorted by position ascending.")
        files["sop.md"] = "\n".join(rules) + "\n"
        q = (f"Build the peak table for spectrum.csv following sop.md. Write output/peaks.json as a JSON list like "
             f'[{{"{key}": 1234.5, "height": 456.7}}], sorted by position.')
        answer = json.dumps([{key: p[0], "height": round(p[1], 2)} for p in peaks])
        tol_x = 2 * (xs[1] - xs[0])

        def check(text, peaks=peaks, key=key):
            got = parse_json(text)
            if not isinstance(got, list) or len(got) != len(peaks):
                return False
            pos = []
            for g, (x, h) in zip(got, peaks):
                if not isinstance(g, dict) or not near(g.get(key), x, rel=0, abs_tol=tol_x):
                    return False
                if not near(g.get("height"), h, rel=0.03, abs_tol=3):
                    return False
                pos.append(float(g[key]))
            return pos == sorted(pos)

        raw = _pick(xs, ys, thr, win)
        wrong = [json.dumps([{key: p[0], "height": p[1]} for p in raw]),
                 json.dumps([{key: p[0], "height": p[1]} for p in peaks[:-1]])]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/peaks.json", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/peaks.json")


# --------------------------------------------------------------------------- dilution plan
def _plain(v):
    """6 significant digits, never in exponent notation."""
    return f"{float(f'{v:.6g}'):f}".rstrip("0").rstrip(".")


CONC_U = {"M": 1e6, "mM": 1e3, "uM": 1.0, "nM": 1e-3}


class DilutionPlan:
    NAME = "dilution-plan"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        cmpd = rng.choice([("ATP", 507.18), ("NaCl", 58.44), ("ampicillin", 349.41), ("glucose", 180.16),
                           ("Tris", 121.14), ("doxorubicin", 543.52), ("EDTA", 292.24)])
        n = rng.randint(4, 6)
        if level == 1:
            stock_uM = rng.choice([10, 20, 50, 100]) * 1000.0  # 10-100 mM
            targets = sorted({round(stock_uM * rng.uniform(0.002, 0.2), -1) for _ in range(n + 3)}, reverse=True)[:n]
            vols = [rng.choice([200, 500, 1000, 1500, 2000]) for _ in targets]
            tab = []
            for i, (c, v) in enumerate(zip(targets, vols)):
                u = rng.choice(["uM", "nM", "mM"])
                tab.append([f"T{i + 1}", _plain(c / CONC_U[u]), u, str(v)])
            plan = []
            for (tid, _, _, v), c in zip(tab, targets):
                s = c / stock_uM * float(v)
                plan.append((tid, s, float(v) - s))
            files = {"targets.csv": rows_to_csv(["tube", "target_conc", "unit", "final_volume_uL"], tab),
                     "reagent.txt": f"Stock: {cmpd[0]} at {stock_uM / 1000:g} mM in water.\n"
                                    "Every tube is made directly from the stock, topped up with water.\n"}
            q = ("Write the pipetting plan for targets.csv using the stock in reagent.txt: output/plan.csv with "
                 "columns tube,stock_uL,diluent_uL (volumes in microlitres).")
            header = ["tube", "stock_uL", "diluent_uL"]
            answer = rows_to_csv(header, [[t, f"{s:.4f}", f"{d:.4f}"] for t, s, d in plan])
            truth = {t: (s, d) for t, s, d in plan}
            wrong = [rows_to_csv(header, [[t, f"{s * 1000:.4f}", f"{d:.4f}"] for t, s, d in plan])]
            cols = ("stock_ul", "diluent_ul")
        else:
            mgml = rng.choice([1, 2, 5, 10, 20, 25])
            stock_uM = mgml / cmpd[1] * 1e6  # g/L / (g/mol) = mol/L
            factor = rng.choice([2, 3, 4, 5, 10])
            first = stock_uM / rng.uniform(5, 40)
            concs = [first / factor ** i for i in range(n)]
            keep = [rng.choice([100, 150, 200, 250, 300, 500]) for _ in range(n)]
            tab = []
            for i, (c, v) in enumerate(zip(concs, keep)):
                u = rng.choice(["uM", "nM"])
                tab.append([f"D{i + 1}", _plain(c / CONC_U[u]), u, str(v)])
            cs = [float(t[1]) * CONC_U[t[2]] for t in tab]
            # backwards: tube k must keep keep[k] after giving transfer to k+1
            trans = [0.0] * n
            dil = [0.0] * n
            nxt = 0.0
            for k in range(n - 1, -1, -1):
                total = float(tab[k][3]) + nxt
                src = stock_uM if k == 0 else cs[k - 1]
                trans[k] = total * cs[k] / src
                dil[k] = total - trans[k]
                nxt = trans[k]
            plan = [(tab[k][0], "stock" if k == 0 else tab[k - 1][0], trans[k], dil[k]) for k in range(n)]
            files = {"series.csv": rows_to_csv(["tube", "target_conc", "unit", "volume_needed_uL"], tab),
                     "reagent.txt": (f"Stock: {cmpd[0]} (molar mass {cmpd[1]} g/mol) at {mgml} mg/mL in buffer.\n"
                                     "Serial dilution: D1 is made from the stock; every later tube is made from the "
                                     "tube before it (D2 from D1, D3 from D2, ...), topped up with buffer.\n"
                                     "volume_needed_uL is what must REMAIN in each tube after you have taken out what "
                                     "the next tube needs.\n")}
            q = ("Write the serial-dilution pipetting plan for series.csv and reagent.txt: output/plan.csv with columns "
                 "tube,source,transfer_uL,diluent_uL, where source is 'stock' or the tube it is drawn from and volumes "
                 "are in microlitres.")
            header = ["tube", "source", "transfer_uL", "diluent_uL"]
            answer = rows_to_csv(header, [[t, s, f"{a:.4f}", f"{d:.4f}"] for t, s, a, d in plan])
            truth = {t: (a, d, s) for t, s, a, d in plan}
            naive = []
            for k in range(n):
                v = float(tab[k][3])
                src = stock_uM if k == 0 else cs[k - 1]
                naive.append([tab[k][0], plan[k][1], f"{v * cs[k] / src:.4f}", f"{v - v * cs[k] / src:.4f}"])
            wrong = [rows_to_csv(header, naive)]
            cols = ("transfer_ul", "diluent_ul")

        def check(text, truth=truth, cols=cols, level=level):
            got = keyed(parse_csv(text), "tube")
            if got is None or set(got) != set(truth):
                return False
            for t, vals in truth.items():
                r = got[t]
                if not near(r.get(cols[0]), vals[0], rel=0.005, abs_tol=0.01):
                    return False
                if not near(r.get(cols[1]), vals[1], rel=0.005, abs_tol=0.01):
                    return False
                if level == 2 and r.get("source", "").lower() != vals[2].lower():
                    return False
            return True

        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/plan.csv", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/plan.csv")


# --------------------------------------------------------------------------- pharmacokinetics
class PkFit:
    NAME = "pk-fit"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        k = rng.uniform(0.06, 0.35)
        ka = k * rng.uniform(4, 10)
        scale = rng.uniform(200, 3000)
        sched = [0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24]
        if k < 0.12:
            sched += [36, 48]
        conc = []
        for t in sched:
            c = scale * ka / (ka - k) * (math.exp(-k * t) - math.exp(-ka * t)) * rng.uniform(0.97, 1.03)
            conc.append(float(f"{c:.4g}"))
        lloq = None
        blq = set()
        if level == 2:
            lloq = float(f"{max(conc) * rng.uniform(0.02, 0.04):.3g}")
            blq = {i for i, c in enumerate(conc) if c < lloq}
            # ensure at least one early BLQ (before tmax) and one late
            if 0 not in blq:
                conc[0] = float(f"{lloq * rng.uniform(0.3, 0.8):.3g}")
                blq.add(0)
            last = len(conc) - 1
            if last not in blq:
                sched.append(sched[-1] + 12)
                conc.append(float(f"{lloq * rng.uniform(0.3, 0.8):.3g}"))
                blq.add(last + 1)
        # reference
        tmax_i = max((i for i in range(len(conc)) if i not in blq), key=lambda i: conc[i])
        pts = [(0.0, 0.0)]
        for i, (t, c) in enumerate(zip(sched, conc)):
            if i in blq:
                if i < tmax_i:
                    pts.append((t, 0.0))
                continue
            pts.append((t, c))
        auc = sum((t2 - t1) * (c1 + c2) / 2 for (t1, c1), (t2, c2) in zip(pts, pts[1:]))
        term = [(t, c) for t, c in pts if c > 0][-4:]
        m, _ = _ols([t for t, _ in term], [math.log(c) for _, c in term])
        kel = -m
        truth = {"k_el_per_h": kel, "half_life_h": math.log(2) / kel, "auc_0_last": auc,
                 "auc_0_inf": auc + term[-1][1] / kel, "cmax": conc[tmax_i], "tmax_h": sched[tmax_i]}
        drug = rng.choice(["DX-114", "compound 7b", "RT-2209", "metoprolol", "candidate A"])
        if level == 1:
            files = {"plasma.csv": "time_h,conc_ng_mL\n" + "".join(f"{t:g},{c:g}\n" for t, c in zip(sched, conc))}
        else:
            dose = datetime(2026, rng.randint(1, 12), rng.randint(1, 27), rng.randint(18, 23), rng.choice([0, 10, 20, 30, 40, 50]))
            lines = ["sample,collected_at,result,unit,comment"]
            for i, (t, c) in enumerate(zip(sched, conc)):
                when = (dose + timedelta(hours=t)).strftime("%Y-%m-%d %H:%M")
                if i in blq:
                    lines.append(f"P{i + 1:02d},{when},BLQ,ng/mL,below LLOQ")
                elif rng.random() < 0.35:
                    lines.append(f"P{i + 1:02d},{when},{c / 1000:.7g},ug/mL,batch 2")
                else:
                    lines.append(f"P{i + 1:02d},{when},{c:g},ng/mL,")
            files = {"plasma.csv": "\n".join(lines) + "\n",
                     "dosing.txt": f"Single oral dose of {drug} given {dose.strftime('%Y-%m-%d %H:%M')} (same clock as collected_at).\n"
                                   f"LLOQ {lloq:g} ng/mL. Convert every result to ng/mL before analysis.\n"}
        files["sap.md"] = "\n".join([
            "# Non-compartmental analysis plan", "",
            "- Time is hours after the dose; the concentration at time 0 is 0 (oral dose).",
            "- BLQ results before Cmax count as 0; BLQ results after Cmax are excluded." if level == 2 else
            "- All results are quantifiable.",
            "- Cmax/Tmax: the highest observed concentration and its time.",
            "- AUC_0-last: linear trapezoidal rule from time 0 to the last quantifiable sample.",
            "- k_el: minus the slope of an ordinary least-squares fit of ln(concentration) against time over the "
            "last 4 quantifiable samples. Half-life = ln(2)/k_el.",
            "- AUC_0-inf = AUC_0-last + C_last / k_el, where C_last is the last quantifiable concentration.",
        ]) + "\n"
        q = (f"Run the non-compartmental analysis in sap.md on plasma.csv ({drug}) and write output/pk.json with keys "
             "k_el_per_h, half_life_h, auc_0_last, auc_0_inf (ng*h/mL), cmax (ng/mL) and tmax_h.")
        answer = json.dumps({kk: round(v, 6) for kk, v in truth.items()})

        def check(text, truth=truth):
            got = parse_json(text)
            if not isinstance(got, dict):
                return False
            got = {str(kk).lower(): v for kk, v in got.items()}
            return all(near(got.get(kk), v, rel=0.01, abs_tol=1e-6) for kk, v in truth.items())

        wrong = [json.dumps({**truth, "half_life_h": 0.5 / truth["k_el_per_h"]}),
                 json.dumps({**truth, "auc_0_inf": truth["auc_0_last"]})]
        return Built(question=q, files=files, check=graded(check), answer=answer,
                     answer_hint="output/pk.json", budget=16 if level == 1 else 20,
                     wrong=[w for w in wrong if not check(w)], deliverable="output/pk.json")
