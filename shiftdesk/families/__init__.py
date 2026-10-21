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
from .v4_math import BoardGame, ClaimCheck, LinearSystem, Recurrence
from .v4_media import AudioAudit, ImageAudit, MarkdownHtml, SrtRetime
from .v4_science import AssayReduction, DilutionPlan, PeakPicking, PkFit
from .v4_security import DecodeChain, JwtInspect, SshdAudit, WebForensics


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
# v4: terminal file-deliverable families for the four domains that scored zero
V4 = [
    AssayReduction, PeakPicking, DilutionPlan, PkFit,          # natural science
    LinearSystem, Recurrence, ClaimCheck, BoardGame,           # math and formal reasoning
    WebForensics, DecodeChain, SshdAudit, JwtInspect,          # cybersecurity
    SrtRetime, ImageAudit, AudioAudit, MarkdownHtml,           # media and content production
]
ALL = ALL + V4
FAMILIES = {f.NAME: f for f in ALL}


def task_ids():
    return [f"{f.NAME}-L{lvl}" for f in ALL for lvl in f.LEVELS]


def v4_task_ids():
    return [f"{f.NAME}-L{lvl}" for f in V4 for lvl in f.LEVELS]


def parse_task_id(task_id):
    if not isinstance(task_id, str) or "-L" not in task_id:
        raise ValueError(f"unknown task_id: {task_id!r}")
    name, level = task_id.rsplit("-L", 1)
    fam = FAMILIES.get(name)
    if fam is None or not level.isdigit() or int(level) not in fam.LEVELS:
        raise ValueError(f"unknown task_id: {task_id!r}")
    return fam, int(level)


# The v4 training list submitted to the arena: every new file-deliverable task (60%) plus the v3 tasks of the
# domains that already scored (software, industrial, office, finance) so they do not regress (36%).
_KEEP_V3 = {"software-engineering", "industrial-physical-systems", "office-white-collar", "finance-economics"}
# The arena accepts at most 50 tasks per submission: 32 new + 18 v3.
_DROP_V3 = {"fifo-basis-L1", "bond-desk-L1", "line-oee-L2", "npv-choice-L1", "meeting-slot-L1"}


def _round_robin(ids):
    by = {}
    for t in ids:
        by.setdefault(parse_task_id(t)[0].DOMAIN, []).append(t)
    out, queues = [], list(by.values())
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


def train_v4():
    """Interleaved so that a run cut short still trains every domain: about three new tasks per two old."""
    new = _round_robin(v4_task_ids())
    old = _round_robin([f"{f.NAME}-L{lvl}" for f in ALL if f not in V4 and f.DOMAIN in _KEEP_V3
                        for lvl in f.LEVELS if f"{f.NAME}-L{lvl}" not in _DROP_V3])
    out, i, j = [], 0, 0
    while i < len(new) or j < len(old):
        if i < len(new) and (j >= len(old) or i * 2 <= j * 3):
            out.append(new[i]); i += 1
        else:
            out.append(old[j]); j += 1
    return out
