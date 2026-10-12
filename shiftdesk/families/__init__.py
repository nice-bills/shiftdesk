"""Task registry. A task id is <family>-L<level>."""
from . import fin, ind, math_, med, off, sci, sec, sw
from .finance import BondDesk, FifoBasis, NpvChoice
from .industrial import BomExplosion, TankBalance
from .mathx import Congruences, ExactProbability, LogicGrid, ShortestRoute
from .media import EditTimeline, HeadlineStyle
from .office import InvoiceMatch, MeetingSlot
from .science import BeerLambert, Stoichiometry
from .security import FirewallAudit, VulnTriage
from .software import ChangeImpact, VersionResolve


class _Legacy:
    """v1 family module, kept at its hardest levels."""

    def __init__(self, mod, levels):
        self.NAME, self.DOMAIN, self.LEVELS, self._mod = mod.NAME, mod.DOMAIN, levels, mod

    def build(self, level, rng):
        return self._mod.build(level, rng)


ALL = [
    # software engineering
    ChangeImpact, VersionResolve, _Legacy(sw, (3,)),
    # industrial and physical systems
    BomExplosion, TankBalance, _Legacy(ind, (2, 3)),
    # natural science
    BeerLambert, Stoichiometry, _Legacy(sci, (3,)),
    # office and white-collar
    MeetingSlot, InvoiceMatch, _Legacy(off, (3,)),
    # finance and economics
    NpvChoice, BondDesk, FifoBasis, _Legacy(fin, (3,)),
    # math and formal reasoning
    Congruences, LogicGrid, ShortestRoute, ExactProbability, _Legacy(math_, (3,)),
    # cybersecurity
    FirewallAudit, VulnTriage, _Legacy(sec, (3,)),
    # media and content production
    EditTimeline, HeadlineStyle, _Legacy(med, (3,)),
]
FAMILIES = {f.NAME: f for f in ALL}


def task_ids():
    return [f"{f.NAME}-L{lvl}" for f in ALL for lvl in f.LEVELS]


def parse_task_id(task_id):
    if not isinstance(task_id, str) or "-L" not in task_id:
        raise ValueError(f"unknown task_id: {task_id!r}")
    name, level = task_id.rsplit("-L", 1)
    fam = FAMILIES.get(name)
    if fam is None or not level.isdigit() or int(level) not in fam.LEVELS:
        raise ValueError(f"unknown task_id: {task_id!r}")
    return fam, int(level)
