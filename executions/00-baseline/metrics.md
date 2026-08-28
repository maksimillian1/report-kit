# Baseline — Metrics

> **Provenance Legend:**
> **Measured** (read from instrument) · **Derived** (arithmetic on other rows) · **Recorded** (hand-written at the time) · **Estimated** (modeled, carries reference value).

| Ref | Domain | What it measures | Exposed Metric Name | Provenance | Status | Required Selector / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| E1 | Compute | CPU Utilization | `container_cpu_usage_seconds_total` | Measured | active | `{namespace="prod", container="app"}` |
| E2 | Compute | Memory Usage | `container_memory_working_set_bytes` | Measured | active | `{namespace="prod", container="app"}` |
| E3 | Network | Ingress Bytes | `container_network_receive_bytes_total` | Measured | active | Filter out system namespaces |
| E4 | Network | Egress Bytes | `container_network_transmit_bytes_total` | Measured | active | Filter out system namespaces |
| E5 | Storage | Disk IOPS | `node_disk_written_bytes_total` | Measured | active | Sum by instance ID |
