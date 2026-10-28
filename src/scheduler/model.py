"""Independent single-processor task/job model; all durations are simulation units."""
from dataclasses import dataclass, field
import math

EPS = 1e-9
CRITICALITY = {"critical": 0, "high": 1, "normal": 2, "low": 3}
TERMINAL = {"completed", "rejected", "deadline_missed", "failed"}
TRANSITIONS = {
    "created": {"pending"}, "pending": {"ready", "rejected", "deferred", "deadline_missed"},
    "deferred": {"ready", "rejected", "deadline_missed"},
    "ready": {"running", "preempted", "deferred", "failed", "deadline_missed"},
    "running": {"ready", "preempted", "suspended", "completed", "failed", "deadline_missed"},
    "preempted": {"running", "ready", "deferred", "failed", "deadline_missed"},
    "suspended": {"ready", "failed", "deadline_missed"},
}


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"Invalid {name}")
    return value


@dataclass(frozen=True)
class Phase:
    phase_id: str
    wcet: float
    mechanisms: tuple[str, ...] = ("light", "medium", "strong")
    minimum_level: int = 1
    quantum: float | None = None
    preemptible: bool = True
    base_category: str = "base"

    def __post_init__(self):
        if not isinstance(self.phase_id, str) or not self.phase_id:
            raise ValueError("Invalid phase ID")
        number(self.wcet, "phase WCET", True)
        if not self.mechanisms or len(set(self.mechanisms)) != len(self.mechanisms):
            raise ValueError("Invalid mechanisms")
        if isinstance(self.minimum_level, bool) or self.minimum_level not in (1, 2, 3):
            raise ValueError("Invalid phase protection")
        if not isinstance(self.preemptible, bool): raise ValueError("Invalid preemption flag")
        if self.base_category not in {"base", "mandatory_validation"}: raise ValueError("Invalid cost category")
        if self.quantum is not None: number(self.quantum, "quantum", True)

    def chunks(self):
        q = self.quantum if self.preemptible and self.quantum else self.wcet
        n = max(1, math.ceil(self.wcet / q - EPS))
        # Equal fixed chunks ensure the requested quantum is an upper bound.
        return [self.wcet / n] * n


@dataclass(frozen=True)
class Task:
    task_id: str
    phases: tuple[Phase, ...]
    period: float
    deadline: float
    release: float = 0
    kind: str = "periodic"
    arrivals: tuple[float, ...] = ()
    criticality: str = "normal"
    safety_critical: bool = False
    minimum_level: int = 1
    exposure: float | None = 0.1
    impact: float = 1.0
    max_preemptions: int = 100
    actual_factor: float = 1.0
    sensor_type: str = "simulated"

    def __post_init__(self):
        if not isinstance(self.task_id, str) or not self.task_id: raise ValueError("Invalid task ID")
        for name in ["period", "deadline", "actual_factor"]: number(getattr(self, name), name, True)
        number(self.release, "release")
        if self.deadline > self.period: raise ValueError("Only constrained deadlines supported")
        if not self.phases or len({p.phase_id for p in self.phases}) != len(self.phases): raise ValueError("Invalid phase IDs")
        if self.kind not in {"periodic", "sporadic", "oneshot"}: raise ValueError("Invalid release model")
        if self.criticality not in CRITICALITY or not isinstance(self.safety_critical, bool): raise ValueError("Invalid criticality")
        if isinstance(self.minimum_level, bool) or self.minimum_level not in (1, 2, 3): raise ValueError("Invalid protection")
        if not isinstance(self.max_preemptions, int) or isinstance(self.max_preemptions, bool) or self.max_preemptions < 0: raise ValueError("Invalid preemption cap")
        for value in [self.impact] + ([] if self.exposure is None else [self.exposure]):
            number(value, "risk")
            if value > 1: raise ValueError("Risk must be normalized")
        if self.kind == "sporadic":
            for t in self.arrivals: number(t, "sporadic release")
            if any(t < self.release for t in self.arrivals) or any(b-a < self.period-EPS for a,b in zip(self.arrivals, self.arrivals[1:])):
                raise ValueError("Sporadic minimum inter-arrival violation")
        elif self.arrivals: raise ValueError("Explicit arrivals only for sporadic tasks")

    @property
    def protected(self):
        return self.safety_critical or self.criticality in {"critical", "high"}

    def releases(self, horizon):
        if self.kind == "sporadic": return [t for t in self.arrivals if t < horizon]
        if self.kind == "oneshot": return [self.release] if self.release < horizon else []
        n = max(0, math.ceil((horizon-self.release) / self.period - EPS))
        return [self.release + k*self.period for k in range(n)]


@dataclass
class Job:
    task: Task
    index: int
    release: float
    state: str = "created"
    cursor: int = 0
    admitted: bool = False
    start: float | None = None
    finish: float | None = None
    preemptions: int = 0
    switches: int = 0
    previous: str | None = None
    last_switch: float = -1e30
    costs: dict = field(default_factory=dict)
    transitions: list = field(default_factory=list)
    plan: list = field(default_factory=list)
    reservation_peak: float = 0
    needs_resume: bool = False

    def __post_init__(self):
        self.plan = [(p, c) for p in self.task.phases for c in p.chunks()]

    @property
    def job_id(self): return f"{self.task.task_id}:{self.index}"
    @property
    def deadline(self): return self.release + self.task.deadline
    @property
    def remaining_base(self): return sum(c for _,c in self.plan[self.cursor:])

    def transition(self, new, now, reason):
        if new not in TRANSITIONS.get(self.state, set()): raise ValueError(f"Illegal {self.state}->{new}")
        self.transitions.append({"time": now, "from": self.state, "to": new, "reason": reason})
        self.state = new


def generate_jobs(tasks, horizon):
    number(horizon, "horizon", True)
    if len({t.task_id for t in tasks}) != len(tasks): raise ValueError("Duplicate task ID")
    return sorted([Job(t, i, r) for t in tasks for i,r in enumerate(t.releases(horizon))],
                  key=lambda j: (j.release, CRITICALITY[j.task.criticality], j.job_id))
