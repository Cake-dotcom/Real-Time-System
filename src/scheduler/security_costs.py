"""Canonical fixed-point cost ledger, shared by planning and execution."""
from dataclasses import dataclass
from src.scheduler.model import number


@dataclass(frozen=True)
class Mechanism:
    name: str
    level: int
    execution_ratio: float
    startup: float
    teardown: float
    switch: float
    preemption: float
    resume: float
    effectiveness: float
    capabilities: tuple[str, ...] = ("integrity",)
    provenance: str = "configured simulation estimate; not measured crypto WCET"

    def __post_init__(self):
        if not self.name or self.level not in (1,2,3): raise ValueError("Invalid mechanism")
        for name in ["execution_ratio", "startup", "teardown", "switch", "preemption", "resume", "effectiveness"]:
            number(getattr(self,name), name)
        if self.effectiveness > 1: raise ValueError("Invalid effectiveness")


def default_registry(scale=1.0):
    number(scale, "cost scale")
    return {name: Mechanism(name, level, ratio*scale, q*scale, q*scale, q*scale,
                           .02*scale, .02*scale, efficacy)
            for name,level,ratio,q,efficacy in [("light",1,.02,.02,.25),
                ("medium",2,.08,.05,.60),("strong",3,.16,.10,.90)]}


def chunk_cost(base, mechanism, previous=None, *, resumed=False, decision=0.0):
    number(base, "base"); number(decision, "decision")
    return {"base": base, "security_execution": base*mechanism.execution_ratio,
            "startup": mechanism.startup, "teardown": mechanism.teardown,
            "switch": mechanism.switch if previous is not None and previous != mechanism.name else 0.0,
            "resume": mechanism.resume if resumed else 0.0,
            "preemption": 0.0, "scheduler": decision}


def total(cost): return sum(cost.values())
