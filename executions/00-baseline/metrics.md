# Baseline — Metrics

> **Provenance** — unmarked = measured · ᴰ derived · ᴿ recorded · ᴱ estimated
> (`methodology.md` §5).

**Refs defined here are global and permanent.** They are never renumbered, never reused,
never re-listed in an execution's `metrics.md`, and never redefined with a different
selector. The selector below is the metric's **canonical** scope; an execution narrowing it
does so in its own §1 Metric Reference Gate, without changing this file.

| Ref | Domain | What it measures | Exposed Metric Name | Provenance | Status | Canonical Selector / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| E1 | Compute | CPU Utilization | `container_cpu_usage_seconds_total` | Measured | active | `{namespace="prod", container="app"}` |
| E2 | Compute | Memory Usage | `container_memory_working_set_bytes` | Measured | active | `{namespace="prod", container="app"}` |
| E3 | Network | Ingress Bytes | `container_network_receive_bytes_total` | Measured | active | Filter out system namespaces |
| E4 | Network | Egress Bytes | `container_network_transmit_bytes_total` | Measured | active | Filter out system namespaces |
| E5 | Storage | Disk IOPS | `node_disk_written_bytes_total` | Measured | active | Sum by instance ID |

**Next free ref:** `E6` · `C1` · `R1` — local execution refs continue this sequence.
