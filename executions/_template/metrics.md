# executions/NN-name/metrics.md

# Execution · ⟨NN-name⟩ — Metrics Register

> **Provenance Legend:**
> **Measured** (read from instrument) · **Derived** (arithmetic on other rows) · **Recorded** (hand-written at the time) · **Estimated** (modeled, carries reference value).

| Ref | Domain | What it measures | Exposed Metric Name | Provenance | Status | Required Selector / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| E1 | Compute | Baseline CPU Inherited | `container_cpu_usage_seconds_total` | Measured | active | Inherited from `00-baseline` · `{namespace="prod"}` |
| E4 | Network | Baseline Egress Inherited | `container_network_transmit_bytes_total` | Measured | active | Inherited from `00-baseline` · Exclude system ns |
| C1 | FinOps | Unit Cost per 1M Executions | `(Total_Cost / Executed_Units) * 1000000` | Derived | active | Formula evaluated post-run using E1, E4 & price basis |
| C2 | Network | Telemetry Overhead Share | `(Telemetry_Bytes / Total_Network_Bytes) * 100` | Derived | active | Evaluated using E3 and E4 |
| R1 | System | Exact UTC Execution Window | `UTC Open -> Close Timestamp` | Recorded | active | Hand-recorded at CLI start/stop due to ingestion lag |
| R2 | Bottleneck | Primary Saturation Point | `Target Component & Metric` | Recorded | active | Manual observation during saturation phase |
