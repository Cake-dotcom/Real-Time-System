"""Exposure scores are scenario assumptions, never calibrated attack probabilities."""
from dataclasses import dataclass
from src.scheduler.model import number


@dataclass(frozen=True)
class RiskEvent:
    time: float
    task_id: str
    exposure: float | None
    confident: bool = True

    def __post_init__(self):
        number(self.time, "risk event time")
        if not isinstance(self.task_id, str) or not self.task_id or not isinstance(self.confident,bool): raise ValueError("Invalid risk event")
        if self.exposure is not None:
            number(self.exposure, "exposure")
            if self.exposure > 1: raise ValueError("Exposure exceeds one")


@dataclass(frozen=True)
class Policy:
    low: float = .3
    high: float = .7
    hysteresis: float = .05
    dwell: float = 5.0
    ttl: float = 100.0
    alpha: float = 1.0
    beta: float = .15
    gamma: float = .3
    decision_cost: float = .001
    admission: bool = True
    reservations: bool = True
    overload: bool = True
    preemption: bool = True
    switch_aware: bool = True
    dynamic: bool = True
    mode: str = "RA-LP-EDF"

    def __post_init__(self):
        for key in ["low","high","hysteresis","dwell","ttl","alpha","beta","gamma","decision_cost"]: number(getattr(self,key), key)
        if not 0 < self.low < self.high < 1 or self.ttl <= 0 or self.hysteresis >= self.low: raise ValueError("Invalid risk thresholds")
        for key in ("admission","reservations","overload","preemption","switch_aware","dynamic"):
            if not isinstance(getattr(self,key),bool): raise ValueError("Invalid policy flag")
        if self.mode not in {"RA-LP-EDF","Standard-EDF","Static-Sec-EDF","MPS-LP-EDF-structural","SAEDF-style","Highest-security","Minimum-security","No-switch-awareness","RA-LP-EDF-Admission","RA-LP-EDF-Preemption","RA-LP-EDF-Optimized"}:
            raise ValueError("Unknown scheduler mode")


class RiskState:
    def __init__(self, task, policy):
        self.task, self.policy = task, policy
        self.exposure, self.updated, self.confident = task.exposure, 0.0, True
        self.level, self.changed = task.minimum_level, -1e30
        self.history = []

    def update(self, event):
        self.exposure, self.updated, self.confident = event.exposure, event.time, event.confident

    def assess(self, now):
        p = self.policy
        uncertain = self.exposure is None or not self.confident or now-self.updated >= p.ttl
        risk = 1.0 if uncertain else self.exposure*self.task.impact
        required = max(self.task.minimum_level, 1 if risk < p.low else 2 if risk < p.high else 3)
        if required > self.level:
            self.level, self.changed = required, now
        elif required < self.level:
            threshold = p.high if self.level == 3 else p.low
            if now-self.changed >= p.dwell and risk < threshold-p.hysteresis:
                self.level, self.changed = required, now
        value = (risk, self.level, uncertain)
        if not self.history or self.history[-1]["value"] != value:
            self.history.append({"time": now, "value": value})
        return value

