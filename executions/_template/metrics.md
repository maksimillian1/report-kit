# Execution · ⟨NN-name⟩ — Metrics

> **Provenance** — unmarked = measured · ᴰ derived · ᴿ recorded · ᴱ estimated
> (`methodology.md` §5).

**Local refs only.** Refs defined in `00-baseline/metrics.md` are inherited by definition
and are **never re-listed or overridden here** — a repeated ref with a different selector is
a second definition of the same number. This execution's per-run selectors live in
`./index.md` §1 › Metric Reference Gate. Numbering continues the global sequence.

| Ref | Domain | What it measures | Formula / Exposed Name | Provenance | Status | Input Sources / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| C1 | FinOps | Unit Cost per 1M Executions | `(Total_Cost / Executed_Units) * 1000000` | Derived | active | Evaluated post-run from E1, E4 and the baseline price basis |
| C2 | Network | Telemetry Overhead Share | `(Telemetry_Bytes / Total_Network_Bytes) * 100` | Derived | active | Evaluated from E3 and E4 |
| R1 | System | Exact UTC Execution Window | `UTC Open → Close Timestamp` | Recorded | active | Hand-recorded at CLI start/stop due to ingestion lag |
| R2 | Bottleneck | Primary Saturation Point | `Target Component & Metric` | Recorded | active | Manual observation during saturation phase |
