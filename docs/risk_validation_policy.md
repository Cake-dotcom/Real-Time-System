# Risk-to-Additional-Validation Policy

## 1. Purpose

Define how sensor-health evidence influences additional sensor-message
validation and its simulated scheduling cost.

This policy is a proposed implementation step toward the research gap
identified in the research proposal: integrating dynamic risk adaptation
with multi-phase secure scheduling and limited-preemption real-time scheduling.

## 2. Mandatory security invariants

1. Message authentication must always be performed.
2. Replay and sequence checks must always be performed.
3. Authentication failures and replay detections must be rejected.
4. Risk adaptation must never disable, skip, or weaken either mandatory check.
5. Additional validation does not make an unauthenticated or replayed message valid.

## 3. Provisional decision table

| Risk level | Sensor-health evidence | Additional validation | Scheduling treatment |
|---|---|---|---|
| Low | Health model and rule-based checks indicate normal behaviour | Apply the existing standard sensor plausibility checks | Account for mandatory processing and any configured baseline validation cost |
| Medium | Anomalous-reading classification or a non-critical health anomaly | Apply standard checks plus additional temporal-consistency and rate-of-change checks | Add the configured simulated cost of the extra checks; test deadline feasibility |
| High | Faulty classification or multiple independent health anomalies | Apply standard checks plus the available enhanced consistency checks; flag for investigation | Add the configured simulated cost of enhanced checks; apply the documented safe failure policy if the deadline cannot be met |

## 4. Decision precedence

1. Authenticate the message.
2. Check replay and sequence validity.
3. Reject messages that fail either mandatory security check.
4. Evaluate sensor-health evidence for messages that pass mandatory checks.
5. Select the additional-validation level.
6. Account for the selected policy's processing cost.
7. Evaluate scheduling and deadline feasibility.
8. Accept a message only when the existing system's acceptance conditions are satisfied.

A high-risk classification must not override a failed mandatory security check.
If enhanced validation cannot be completed within the applicable deadline,
the system must follow its documented safe failure behaviour rather than
silently skipping validation.

## 5. Cost accounting

All additional-validation costs initially used in experiments are simulated
parameters, not measured execution times.

Record the assumed cost of each validation level explicitly and keep the
parameters configurable. Do not describe these values as measured overhead
unless they have actually been measured on the implementation.

Report simulated validation overhead separately from any measured runtime.

## 6. Experimental status

The risk thresholds, validation rules, and cost parameters are provisional
design choices. They must be implemented, tested, and evaluated against
fixed-policy and baseline scheduling approaches before drawing conclusions.

This policy alone does not establish research novelty or implement the full
multi-phase, limited-preemption scheduling model proposed in the report.
