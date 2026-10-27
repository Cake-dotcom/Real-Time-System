# Session-based source authentication

## Scope and protocol

This is an evaluated integration for the Python vehicle-sensor simulation. It
uses pre-provisioned per-sensor demonstration secrets; it is not a standardized
automotive authentication protocol or production key-management implementation.
The receiver, provisioned key map, clock and administrative actions are trusted.
The attacker may inject, modify, record, replay or reorder network messages.
A stolen sensor secret allows impersonation until administrative revocation; ML
health classification cannot prove the physical origin or truth of a reading.

1. A known, non-revoked sensor requests a challenge. The receiver generates a
   256-bit nonce, 128-bit challenge ID and includes its random 256-bit boot context
   and the source identity. Challenges expire after 5 monotonic seconds.
2. The sender computes HMAC-SHA256 over the canonical, domain-separated challenge
   transcript with its provisioned secret. The receiver verifies using
   `hmac.compare_digest`. Every completion attempt consumes that pending challenge.
3. A successful proof creates a random 256-bit session ID with a 60-second expiry.
   Both sides derive a separate message key using HMAC-SHA256 over the challenge
   and session ID with a distinct purpose label. No message key is transmitted.
4. Every message includes `sensor_id`, `session_id`, `sequence`, timestamp and
   sensor contents. Its HMAC covers the entire canonical message with a third
   purpose label. The receiver checks the session, MAC and sequence on every call.

All tagged data includes a protocol identifier and purpose. Serialization is
sorted-key JSON, compact separators, ASCII escaping, UTF-8 bytes and rejection
of NaN/infinity. Message/proof/key-derivation domains differ. There is no optional
fallback accepting the old long-term-key message MAC when a session is missing.
`message_auth.py` remains available as a standalone HMAC demonstration, but the
live receiver exclusively uses the session-bound protocol.

The standard-library primitives are documented at
[Python secrets](https://docs.python.org/3/library/secrets.html),
[Python hmac](https://docs.python.org/3/library/hmac.html), and
[Python time](https://docs.python.org/3/library/time.html).
These references support the primitives, not certification of this custom protocol.

## Lifecycle, replay and resource bounds

There is at most one active session and pending challenge per source, with default
global capacities of 64 each. New entries fail closed at capacity; live sessions
are not silently evicted. Cleanup runs during operations, removes expired keys
and challenges, and retains at most one non-secret status record per provisioned
identity. Provisioning itself is trusted configuration, not an unauthenticated API.

Sequences must be non-negative integers (not Boolean) and strictly greater than
the last authenticated sequence for that source. The counter survives session
replacement, expiration, session revocation and key rotation. Gaps are allowed;
duplicates and out-of-order delivery are rejected. Invalid MACs do not advance it.
An authenticated reading rejected by health/policy/scheduling still consumes its
sequence, but never updates accepted feature/health histories.

Session revocation removes that session and pending proof; the source may prove
its identity again. Source revocation represents detected credential compromise:
it invalidates sessions/challenges and blocks new handshakes until a trusted
`rotate_source_key` operation provisions a different secret. Invalid network MACs
alone do not trigger source revocation, avoiding a trivial attacker-driven revoke.

Reset generates a fresh boot context, invalidates all sessions/proofs, and clears
sequence state. Old messages cannot authenticate under a new session. Administrative
source revocations survive an in-process reset. On process restart, the deployment
must reload revoked identities using `revoked_sources` and the current provisioned
keys. This prototype has no durable key/revocation database. Fresh process sessions
never inherit trust from previous session IDs. A source can restart its sequence
after a receiver reset only after a new valid proof.

Handshake and verification transitions use a shared reentrant lock. Exceptions
fail closed without exposing their text; a failed renewal cannot replace an
existing valid session. Verification also rechecks expiry before committing sequence
state. Concurrent duplicate delivery permits only one successful verification.

## Integration and timing

The simulated sender performs the proof exchange using `authenticate_sender` and
retains a `SenderSession`. `sensor_system.process_messages` receives signed messages;
it never auto-authenticates an untrusted incoming source with a receiver-held secret.
The dashboard auto-handshakes on a sensor's first submission, then retains its sender
session. Expired/revoked sessions are visibly rejected until explicit reauthentication.
Compromise revocation requires administrative key rotation, not just another proof.

The live path is:

```text
Envelope/source -> active session -> per-message MAC -> source-wide replay check
 -> schema/metadata -> features/health -> NIST-inspired project risk profile
 -> required checks -> EDF/fallback/deadline -> final acceptance/history commit
```

The timing model retains `security_overhead` as the **per-message baseline including
MAC verification**, and adds the one-time simulated handshake cost (2) plus selected
validation cost (0/1/2). All are abstract scheduler units. The receiver, not an
incoming field, determines whether the session is new. Cost 2 is charged to the
first successfully verified message of each session, once; reuse costs 0 for the
handshake, but still incurs the baseline per-message overhead. Failed MAC/replay
attempts do not consume that first-message charge.

Measured nanoseconds are never added directly to simulated costs. The 2-unit
handshake cost is an explicit uncalibrated assumption, not a conversion from the
benchmark. Even an explicitly pre-established session assigns this accounting
charge to its first message. This is an amortization convention, not a claim that
the handshake occurred during that task. Work spent rejecting messages or validating
deferred tasks is not modeled as EDF processor demand. A new-session LIDAR task with
execution 3, baseline 1 and validation 1 finishes at 7; reuse finishes at 5.

Counters distinguish handshake attempts, successful full handshakes, successful
session reuses, failed authentication events, MAC verification attempts, and replay
rejections. `handshake_processing_ns` measures receiver challenge/proof processing;
`message_verification_ns` measures receiver verification using `perf_counter_ns`.
Public audit omits secret keys, message tags and source proofs.

## Benchmark methodology

`src/ml/benchmark_source_auth.py` compares a full new source exchange before every
message against cached sessions, using exactly the same semantic payloads, source
identities, sequences and attack schedule. Session IDs/nonces necessarily differ.
Both modes use the same verifier and enforce source-wide replay across renewals.
The baseline is deliberately repeated source authentication, not the earlier bare
HMAC-only implementation; no speedup relative to that older implementation is claimed.

Defaults: 1,000 valid messages across three sensors plus 50 duplicate and 50 modified
attempts, 10 repetitions per mode, alternating execution order, and a 30-valid-message
warmup per mode excluded from results. Every attempt in both modes reaches a valid
session and MAC verification. Expected attack outcomes and equal MAC counts are
asserted. Initialization and payload generation are excluded equally.

Exchange latency includes both simulated endpoints: challenge/proof, session key
derivation when necessary, sender message MAC and receiver verification. Receiver
latency excludes sender work and sums instrumented receiver sections. Reports give
mean, median, nearest-rank p95, total elapsed time, process CPU time, per-repetition
means, counts and reduction percentages. Total loop time includes measurement and
outcome bookkeeping; individual exchange latency does not. There is no network,
transport, hardware sensor or ECU. Host scheduling noise remains.

## Policy/model evaluation and requirements audit

The existing policy comparison now authenticates sources in all modes and includes
unknown and unauthenticated attempts. Base EDF uses standard plausibility, fixed
validation always runs all available extra checks, and adaptive chooses checks via
the existing risk matrix. All modes share source sessions, per-message MAC/replay,
health rejection, missing-evidence rejection, accepted-history rules and EDF fallback.
It reports misses with denominator, deferrals, rejection counts, overhead components,
escalations and acceptance with failed source/MAC/replay gates. Scenario-level
`rejected` includes deferrals; the top-level field explicitly excludes deferrals.

Saved-model evaluation checks the bundle schema, reports its predictions on the
reconstructed holdout as a provenance-limited diagnostic, and refits clones for
independent run splits without overwriting artifacts. The optional four-fold
leave-one-run-out evaluation exposes variability masked by the single holdout.
Four runs and uncertain dataset feature-generation provenance limit every result.

No separate research proposal file was present in this workspace during inspection.
The supplied requirements and handoff were used for the implementation audit. The
scheduler remains non-preemptive EDF with critical-only fallback. Multi-phase or
limited-preemption scheduling, physical safe-state actuation, formal timing proofs,
production provisioning, mutual receiver authentication, encryption, forward secrecy,
rate limiting, persistent revocations and a reviewed wire transport are not implemented.
The Streamlit demo is a single-process simulation with shared receiver state, not a
multi-tenant authenticated administrative console. UI compromise/revoke controls are
trusted demonstration actions. Do not expose the app as a production control plane.

The legacy login coordinator is repaired by adapting its single demonstration task
to `schedule_message_tasks`, with its original execution 2/deadline 6 and explicit
zero additional scheduling overhead. This restores the broken import without mixing
MFA policy into sensor authentication or changing the EDF scheduler.

See `source_auth_verification.md` for actual results, changed files and commands.
