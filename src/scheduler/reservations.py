"""Deadline-indexed remaining-demand reservations, not a replenishing CBS server."""
from src.scheduler.model import EPS


class ReservationLedger:
    def __init__(self):
        self.entries = {}
        self.events = []
        self.violations = 0
        self.reserved_total = 0.0
        self.consumed_total = 0.0

    def update(self, jobs, budgets, now):
        desired = {j.job_id: {"release": j.release, "deadline": j.deadline,
                   "remaining": budgets[j.job_id]} for j in jobs if j.task.protected}
        for key,value in desired.items():
            previous = self.entries.get(key, {}).get("remaining", 0)
            if value["remaining"] > previous:
                self.reserved_total += value["remaining"]-previous
        if desired != self.entries:
            self.events.append({"time": now, "reservations": desired.copy()})
        self.entries = desired

    def consume(self, job_id, amount):
        if job_id in self.entries:
            self.entries[job_id] = dict(self.entries[job_id])
            self.entries[job_id]["remaining"] -= amount
            self.consumed_total += amount
            if self.entries[job_id]["remaining"] < -EPS: self.violations += 1
