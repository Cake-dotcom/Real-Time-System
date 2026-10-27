# Policy selection and implementation design

Selected before implementation, 2026-10-27.

Official sources, issued by the US National Institute of Standards and Technology:

- **NIST SP 800-30 Rev. 1, Guide for Conducting Risk Assessments** (September 2012):
  https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-30r1.pdf
  Section 3.2, Tasks 2-4/2-5/2-6; Task 2-6 is on printed page 35.
  Appendix I, Table I-2, printed page I-1, supplies the exemplary five-by-five
  likelihood/impact matrix used verbatim by this implementation.
- **NIST SP 800-82 Rev. 3, Guide to Operational Technology (OT) Security**
  (September 2023): https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf
  Sections 4.1.2 (printed pp. 51–53) and 4.1.3 (p. 53) inform consideration of
  physical consequences and selection of risk responses.

These are guidance, not a ready-made sensor validation or EDF algorithm. The
chosen method is a project-specific application of NIST risk assessment, not
NIST certification or a complete organizational risk assessment. Table I-2 is
an exemplary decision matrix, not a mandated numerical score. Neither source
prescribes our thresholds, costs, HMAC protocol, ML model, or scheduling.

## Scope and design

The assessed event is consumption of an unreliable authenticated sensor reading.
Compromised sensors, faults, and errors can produce this event; a health class
does not identify an attacker. HMAC/replay/schema gates remain unconditional.
After those gates, health evidence supplies an explicitly uncalibrated qualitative
overall-likelihood proxy; configured sensor criticality supplies an impact proxy.
The matrix combines them. No ML probability is interpreted as attack likelihood.

Project assumptions: normal -> low likelihood; a deterministic warning -> moderate;
anomalous_reading -> high; faulty -> very high. Criticality 1/2/3 maps to
moderate/high/very-high impact. These proxies need validation against independent
runs and a physical hazard analysis. Normal critical sensors therefore receive
moderate risk and additional checks. Missing model/prediction/features/criticality
means unavailable evidence and no acceptance.

Project responses: very-low/low -> standard plausibility; moderate -> temporal
consistency and plausibility; high -> those checks plus stability; very-high ->
reject. All unhealthy readings remain rejected even if diagnostic extra checks
pass. Unknown evidence defers consumption without an automatic retry queue.
The existing low/medium/high response API remains a compatibility helper; the
live pipeline invokes evidence assessment and the matrix first.

Costs remain 0/1/2 abstract scheduler units for standard/additional/enhanced.
Required checks execute before scheduling; the chosen modeled cost is added once
to eligible tasks. Rejected checks are reported but not scheduled; this simulator
does not model CPU time spent rejecting traffic. Authentication/replay cannot be
overridden by any policy response. Only scheduled, on-time, healthy messages that
passed required checks enter accepted history. Batch features use the history
accepted before the batch; intra-batch readings are not yet trusted evidence.

Dashboard results will expose backend gate results, evidence, policy, checks,
cost, deadline result, and final disposition. Tests will exercise the real backend
and Streamlit form, including attempts to force a permissive policy behind failed
authentication/replay. Model evaluation will preserve both existing artifacts;
any reproduced training uses an in-memory clone and group-separated split.
