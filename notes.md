# Report Kit — Notes

Referenced from `checklist.md`. Read once; the checklist stays terse.

---

## [1] "Scraped and UP"

Prometheus pulls metrics from targets. A component is *scraped* when Prometheus has a
job configured for it, the target is reachable, and the last scrape succeeded.

**Verify — do not read config, query live state:**

````promql
up == 0                      # any failing target
up{job="tei"}                # a specific one; absent result = no job configured at all
````

Or open Prometheus UI → **Status → Targets**. `UP` means reachable, not correct: also
confirm the metric you need actually exists (`{__name__=~"te_.*"}`).

**Absent ≠ zero.** A component with no scrape job returns an empty series, which plots
as nothing and reads as "no load". This is how a real constraint gets missed.

**Adding a target** (kube-prometheus-stack): create a `ServiceMonitor` in the component's
namespace with `labels.release` matching the Helm release, pointing at the metrics port
and path. Then re-check `up{job="<name>"}`.

---

## [2] Resource-hours

Run cost is **computed, not read from a bill**. Billing reports lag ~24h and are
hourly at best; a 20-minute run is invisible in them.

````
$/run = Σ_type ( count(type) × duration_hours × price_per_hour(type) )
````

So the instrumentation requirement is: **how many billable units of each type existed
at each moment of the run.**

````promql
count by (label_node_kubernetes_io_instance_type, label_karpenter_sh_capacity_type) (kube_node_labels)
````

Integrate over the run window (`avg_over_time` × duration, or sum the exported series ×
step). Multiply by on-demand or spot price per type. Prices go in `cost-model.xlsx` and
are the same across projects.

Two things to include, both routinely forgotten:
- **Warm-up nodes** — provisioning + image pull + init are billed and produce zero work.
  Their share of total node-hours is what explains the cost curve turning back up.
- **Consolidation tail** — nodes billed after the last unit of work, before teardown.

Billing exports are still needed — for the idle-floor window (24h, daily granularity),
where they work fine.

---

## [3] Metrics from short-lived workloads

Prometheus is pull-based. A worker that lives 40s against a 30s scrape interval is
sampled once or not at all. Pushgateway is the wrong fix here: values persist after the
job is gone and labels accumulate.

**Pattern: one structured summary line per execution, metrics derived from logs.**

Requirements:
1. Exactly one summary line per process execution.
2. Emitted on **every** exit path — normal completion, exception, and signal. The signal
   path is what the failure-injection run depends on; it is also the one usually missed.
3. Counts are cumulative for that execution, not per batch.

````python
# worker/summary.py — emit once per execution, on every exit path
import atexit, json, os, signal, sys, time

_state = {"units_processed": 0, "bytes_in": 0, "errors": 0,
          "exit_reason": "completed", "started": time.time()}
_emitted = False

def bump(**kw):
    for k, v in kw.items():
        _state[k] = _state.get(k, 0) + v

def _emit():
    global _emitted
    if _emitted:
        return
    _emitted = True
    _state["duration_ms"] = int((time.time() - _state.pop("started")) * 1000)
    _state["worker"] = os.getenv("HOSTNAME", "unknown")
    _state["app"] = os.getenv("APP_NAME", "worker")
    print(json.dumps(_state), flush=True)   # stdout — one line, nothing after it

atexit.register(_emit)                       # normal exit and unhandled exception

def _on_signal(signum, _frame):
    _state["exit_reason"] = signal.Signals(signum).name
    _emit()
    sys.exit(0)

for s in (signal.SIGTERM, signal.SIGINT):
    signal.signal(s, _on_signal)
````

Promtail side — two mistakes that make this silently produce nothing:

````yaml
pipelineStages:
  - match:
      selector: '{namespace="apps"}'        # NOT "default" — match the real namespace
      stages:
        - json:
            expressions:
              units_processed: units_processed
              duration_ms: duration_ms
              exit_reason: exit_reason
        - labels:
            exit_reason:                    # lets you separate interrupted executions
        - metrics:
            worker_units_processed_total:
              type: Counter
              source: units_processed
              config:
                action: add                 # NOT "inc" — inc counts log lines, not units
            worker_execution_duration_ms:
              type: Histogram
              source: duration_ms
              config:
                buckets: [1000, 5000, 15000, 60000, 300000]
````

**Verify before trusting it:** trigger one real execution, then confirm
`increase(worker_units_processed_total[5m])` matches the units that execution actually
handled. Then kill a pod and confirm a summary with `exit_reason="SIGTERM"` appears.
