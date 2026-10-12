"""Natural science v3 families: calibration curves and stoichiometry."""
import math

from ..grading import close, fields, same_text
from .base import Built

DOMAIN = "natural-science"


# ---------------------------------------------------------------- beer-lambert
class BeerLambert:
    NAME = "beer-lambert"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        eps = rng.uniform(0.008, 0.03)  # absorbance per uM
        b0 = rng.uniform(0.004, 0.03)
        n = rng.randint(5, 7)
        concs = sorted(rng.sample(range(5, 80, 5), n))
        blank = round(rng.uniform(0.031, 0.058), 3) if level == 2 else 0.0
        stds = []
        for i, c in enumerate(concs):
            a = eps * c + b0 + rng.gauss(0, 0.004) + blank
            stds.append([f"S{i + 1}", c, round(a, 4)])
        bad = None
        if level == 2:
            bad = rng.choice(stds[1:-1])
            bad[2] = round(bad[2] * rng.choice([1.25, 1.3, 0.72]), 4)
        samples = []
        for j in range(rng.randint(3, 5)):
            c = rng.uniform(concs[0] + 2, concs[-1] - 2)
            dil = rng.choice([1, 2, 5, 10]) if level == 2 else 1
            a = eps * c + b0 + blank
            samples.append([f"U{j + 1}", round(a, 4), dil])
        target = rng.choice(samples)

        use = [s for s in stds if s is not bad]
        xs = [s[1] for s in use]
        ys = [s[2] - blank for s in use]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        icpt = my - slope * mx
        conc = (target[1] - blank - icpt) / slope * target[2]

        # wrong: no exclusion / no blank / no dilution
        xs2 = [s[1] for s in stds]
        ys2 = [s[2] - blank for s in stds]
        mx2, my2 = sum(xs2) / len(xs2), sum(ys2) / len(ys2)
        s2 = sum((x - mx2) * (y - my2) for x, y in zip(xs2, ys2)) / sum((x - mx2) ** 2 for x in xs2)
        i2 = my2 - s2 * mx2
        wrong_c = (target[1] - blank - i2) / s2 * target[2]

        std_csv = "standard,conc_uM,absorbance\n" + "".join(f"{s[0]},{s[1]},{s[2]}\n" for s in stds)
        smp_csv = "sample,absorbance,dilution_factor\n" + "".join(f"{s[0]},{s[1]},{s[2]}\n" for s in samples)
        notes = [
            "Lab notebook, plate reader run",
            "Fit absorbance = slope * conc_uM + intercept by ordinary least squares over the standards.",
            "Sample concentration = (absorbance - intercept) / slope, times the dilution factor.",
        ]
        if level == 2:
            notes += [
                f"All readings are raw. Subtract the reagent blank ({blank} AU) from every standard and every sample first.",
                "",
                f"14:20 correction: standard {bad[0]} was mis-pipetted. Leave it out of the fit.",
            ]
        files = {"standards.csv": std_csv, "samples.csv": smp_csv, "notebook.txt": "\n".join(notes) + "\n"}
        rel = 0.005
        ans = {"slope": round(slope, 6), "concentration_uM": round(conc, 2)}
        check = lambda a: fields(a, {
            "slope": lambda v: close(v, slope, rel=rel),
            "concentration_uM": lambda v: close(v, conc, rel=rel),
        })
        return Built(
            question=(f"Using the calibration standards, find the fitted slope (AU per uM) and the original "
                      f"concentration of sample {target[0]} in uM."),
            files=files,
            check=check,
            answer=ans,
            answer_hint='a JSON object {"slope": 0.012345, "concentration_uM": 41.27} (within 0.5%)',
            budget=10,
            wrong=[{"slope": round(s2, 6), "concentration_uM": round(wrong_c, 2)}] if level == 2 else
                  [{"slope": round(slope, 6), "concentration_uM": round(conc * 1.1, 2)}],
        )


# ---------------------------------------------------------------- stoichiometry
MASSES = {"H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "Na": 22.990, "Cl": 35.45, "S": 32.06,
          "Ca": 40.078, "Fe": 55.845, "Mg": 24.305, "K": 39.098, "P": 30.974}

REACTIONS = [
    # (reactant A, a, reactant B, b, product, c, display)
    ("CH4", 1, "O2", 2, "CO2", 1, "CH4 + 2 O2 -> CO2 + 2 H2O"),
    ("C3H8", 1, "O2", 5, "CO2", 3, "C3H8 + 5 O2 -> 3 CO2 + 4 H2O"),
    ("N2", 1, "H2", 3, "NH3", 2, "N2 + 3 H2 -> 2 NH3"),
    ("Fe2O3", 1, "C", 3, "Fe", 2, "Fe2O3 + 3 C -> 2 Fe + 3 CO"),
    ("CaCO3", 1, "HCl", 2, "CaCl2", 1, "CaCO3 + 2 HCl -> CaCl2 + H2O + CO2"),
    ("Mg", 2, "O2", 1, "MgO", 2, "2 Mg + O2 -> 2 MgO"),
    ("NaOH", 2, "H2SO4", 1, "Na2SO4", 1, "2 NaOH + H2SO4 -> Na2SO4 + 2 H2O"),
    ("C6H12O6", 1, "O2", 6, "CO2", 6, "C6H12O6 + 6 O2 -> 6 CO2 + 6 H2O"),
    ("P4", 1, "O2", 5, "P4O10", 1, "P4 + 5 O2 -> P4O10"),
    ("KOH", 1, "HCl", 1, "KCl", 1, "KOH + HCl -> KCl + H2O"),
]


def molar_mass(formula):
    import re
    total = 0.0
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        total += MASSES[el] * (int(n) if n else 1)
    return total


class Stoichiometry:
    NAME = "stoichiometry"
    DOMAIN = DOMAIN
    LEVELS = (1, 2)

    @staticmethod
    def build(level, rng):
        A, a, B, b, P, c, disp = rng.choice(REACTIONS)
        while True:
            ma = round(rng.uniform(5, 120), 2)
            mb = round(rng.uniform(5, 120), 2)
            pa = rng.choice([92, 95, 97, 98.5]) if level == 2 else 100
            pb = rng.choice([90, 94, 96, 99]) if level == 2 else 100
            na = ma * pa / 100 / molar_mass(A) / a
            nb = mb * pb / 100 / molar_mass(B) / b
            if abs(na - nb) / max(na, nb) > 0.08:
                break
        lim = A if na < nb else B
        ext = min(na, nb)
        yld = ext * c * molar_mass(P)
        eff = rng.choice([72, 81, 88, 93]) if level == 2 else 100
        actual = yld * eff / 100
        nai = ma / molar_mass(A) / a
        nbi = mb / molar_mass(B) / b
        naive = min(nai, nbi) * c * molar_mass(P)
        mass_txt = "Standard atomic masses (g/mol)\n" + "".join(f"{k} {v}\n" for k, v in MASSES.items())
        batch = [f"Reaction: {disp}", f"Charged: {ma} g of {A} and {mb} g of {B}."]
        if level == 2:
            batch += [f"Assay purity: {A} {pa}%, {B} {pb}% (by mass; the rest is inert).",
                      f"Expected isolated yield for this process: {eff}% of theoretical."]
        files = {"atomic_masses.txt": mass_txt, "batch.txt": "\n".join(batch) + "\n"}
        key = "expected_g" if level == 2 else "theoretical_g"
        value = actual if level == 2 else yld
        q = (f"Which reactant limits the batch, and what mass of {P} do you expect"
             f"{' to isolate' if level == 2 else ' in theory'}? Use atomic_masses.txt for molar masses.")
        return Built(
            question=q,
            files=files,
            check=lambda ans: fields(ans, {"limiting": lambda v: same_text(v, lim),
                                           key: lambda v: close(v, value, rel=0.005)}),
            answer={"limiting": lim, key: round(value, 2)},
            answer_hint=f'a JSON object {{"limiting": "<formula>", "{key}": 12.34}} (mass in grams, within 0.5%)',
            budget=8,
            wrong=[{"limiting": (B if lim == A else A), key: round(value, 2)},
                   {"limiting": lim, key: round(naive, 2) if level == 2 else round(value * 0.5, 2)}],
        )
