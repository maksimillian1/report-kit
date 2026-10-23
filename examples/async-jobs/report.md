# Executive Engineering Report — queue drain (example)

> **This is the kit's worked example for the jobs profile, not a real report.**
> Every value comes from a real run on a single-node local cluster — see
> `execution.md` and the files under `scripts/data/`. Nothing here is
> fabricated, which is why the cost sections are empty: a laptop has no price
> basis, and inventing one would teach exactly the wrong lesson.

Legend — ᴰ derived · ᴱ estimated · ᴿ recorded during the run · ᴱˣ excluded

---

## Coverage

| Area | Status | Evidence |
| :--- | :--- | :--- |
| Drain time vs worker pool ceiling | measured | `execution.md` §4 |
| Whether the shared tier is the constraint | **measured, and it is not** | `execution.md` §4, refs D10 / M6 |
| Where the pool's saturation point is | **not found** | `execution.md` §4 Saturation · the grid ends before the system does; sizing above `n = 8` is unsupported |
| Ramp vs contention above `n = 4` | **declared, not separated** | `execution.md` §4 · the missing 38<!--VD34--> % of per-worker efficiency has two candidate causes and no verdict |
| Cost per unit drained | **declared, not measured** | No price basis exists for a local cluster |
| Behaviour under worker loss | **out of scope** | A pod killed mid-unit would be caught by `G1`; it never happened, so nothing is claimed |
| Node autoscaling and instance interruption | **out of scope** | `kind` cannot create or reclaim nodes; the real jobs profile's validity logic stays untested |

---

## 1. BLUF

Raising the worker pool ceiling from 1<!--VR5--> to 8<!--VR8--> cuts the drain
of 1,200<!--VR1--> units from **294<!--VD1--> s to 60<!--VD4--> s** — a
4.9<!--VD19-->× speed-up for 8<!--VR8-->× the workers, with per-worker
efficiency falling from 100<!--VD21--> % to 62<!--VD24--> %.

**No ceiling was found**, and the component predicted to be the ceiling is
provably not one: the shared tier never stayed at its own replica maximum for
a whole drain, and at `n = 1` never left one replica, while its service time
moved 1<!--VD26--> % against a 394<!--VD27--> % rise in throughput. Adding workers was still buying throughput where this grid stops.

**The prediction failed because it priced the wrong resource.** The tier costs
60<!--VR4--> ms of wall time per unit, not 60<!--VR4--> ms of exclusive CPU — a
latency, not a capacity. That distinction is the transferable finding here; the drain numbers
belong to one laptop.

---

## 2. Test Setup & Scope

One unit is one queue message: 150<!--VR3--> ms of worker time, then one call
to the shared tier costing 60<!--VR4--> ms of its time. One unit in twenty fails after the burn
and is requeued exactly once — **deterministically**, so that every point on
the grid does identical work.

Arrivals are offered at a **constant rate** (40<!--VR2--> units/s), open model, and the
producer runs concurrently with the measurement. A producer paced by the drain
could not build a backlog, and the backlog is the thing under test.

| | |
| :--- | :--- |
| Scope | worker pool 0–8, `600m` CPU limit each; shared tier 1–2 replicas at `500m` |
| Unit cost of work | 150<!--VR3--> ms worker + 60<!--VR4--> ms shared tier, both wall-clock |
| Measured range | pool ceiling 1<!--VR5--> – 8<!--VR8-->, 1,200<!--VR1--> units per point, 40<!--VR2--> units/s offered |
| Not covered | pool ceilings above 8, unit counts scaled per point, a non-deterministic failure share, sustained arrival rates above the drain rate |

---

## 3. Efficiency Frontier

### 3.1 Run matrix

| Pool ceiling | D8 drain | D9 units/s | Speed-up | Per-worker efficiency | D10 tier service | Saturation signal |
| ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 1<!--VR5--> | 294.1<!--VD1--> s | 4.08<!--VD6--> | 1.00<!--VD16-->× | 100<!--VD21--> % | 81.6<!--VD11--> ms | baseline ᴿ |
| 2<!--VR6--> | 159.2<!--VD2--> s | 7.54<!--VD7--> | 1.85<!--VD17-->× | 92<!--VD22--> % | 80.2<!--VD12--> ms | near-linear ᴿ |
| 4<!--VR7--> | 87.5<!--VD3--> s | 13.71<!--VD8--> | 3.36<!--VD18-->× | 84<!--VD23--> % | 75.5<!--VD13--> ms | efficiency decaying ᴿ |
| 8<!--VR8--> | 59.6<!--VD4--> s | 20.14<!--VD9--> | 4.94<!--VD19-->× | 62<!--VD24--> % | 82.5<!--VD14--> ms | still climbing ᴿ |
| 8<!--VR8--> (repeat) | 53.4<!--VD5--> s | 22.46<!--VD10--> | 5.50<!--VD20-->× | 69<!--VD25--> % | 82.6<!--VD15--> ms | ±10<!--VD28--> % on the same point ᴿ |

A five-point first pass at 400<!--VR9--> units per point is excluded: its drains were
short enough that the autoscaler's ramp was most of the measurement. See
`execution.md` §3 note #05 — it is the most instructive row in this example.

### 3.2 Chart

`charts/drain.svg` — `report-kit charts --all`, kind `line` in `charts/charts.yaml`, from a CSV
that transcribes §3.1 above.

One panel, because `units/s` is the only unit in the file. A sweep that measured
throughput and never priced it charts its throughput; the cost panel would have
appeared on its own had there been a column in dollars, and §4 says why there is
not.

The repeat at ceiling 8<!--VR8--> is its own row, which is why the line ends in a
short vertical rise: that is the grid's own ±10<!--VD28--> % spread, drawn rather
than described.

### 3.3 Knee · sweet spot · waste boundary

| | Pool ceiling | Read from |
| :--- | ---: | :--- |
| **Sweet spot** | 2<!--VR6--> | 92<!--VD22--> % per-worker efficiency, still near-linear |
| **Knee** | between 4<!--VR7--> and 8<!--VR8--> | efficiency falls from 84<!--VD23--> to 62<!--VD24--> % across this interval, after 8<!--VD33--> points between 2 and 4 |
| **Throughput peak** | **not reached** | still climbing at 8<!--VR8-->, which is where the rig stops |
| **Waste boundary** | not established | needs a grid that reaches saturation |

The sweet spot is where a worker is still worth what it costs, not where the
queue drains fastest. Those are different rows, and on this grid they are at
opposite ends of it.

### 3.4 Shape of the cost curve

Per-worker efficiency decays from the second point onward — there is no flat
region where workers are free. What the grid does not show is a *turn*:
efficiency is falling, faster across the top interval, and throughput is still rising, so nothing here
identifies a rate beyond which adding workers stops paying, only a rate beyond
which each one pays less.

### 3.5 Constraint ladder

**No tier is proven, and the one that was expected is ruled out.**

The shared tier was built to be the first ceiling: capped at two replicas,
60<!--VR4--> ms per call, sized to cap throughput near 16.7<!--VE1--> units/s.
It did not. It reached its replica maximum (`M6 = 2`) only partway through each
drain, and never at `n = 1`, while throughput reached 20.1<!--VD9--> units/s, and its
own service time (`D10`) rose 1<!--VD26--> % against a 394<!--VD27--> % rise in load. A tier being *relieved* is what proves the tier below it; this one was
never binding, so there is nothing to relieve.

**Two candidates remain for the decaying efficiency, and this grid separates
neither**: the autoscaler's ramp, which is 15–30 s of a 60<!--VD4--> s drain at the top
of the grid, and CPU contention on a shared laptop. Telling them apart needs
the unit count scaled with the pool ceiling so that every point's drain
contains a comparable steady segment — a different execution, named here
rather than guessed at.

---

## 4. Cost Structure

**Not measured.** A local single-node cluster has no price basis and no
attribution tags. The jobs profile's cost pass — `report-kit node-cost` over
the point's window — is exactly the part this example cannot exercise, because
it needs a node autoscaler creating and destroying billable instances.

In a real report this section is where the §3.1 matrix stops being about
seconds. A drain that is 4.9<!--VD19-->× faster on 8<!--VR8-->× the workers costs more per unit,
not less, unless the instances are reclaimed the moment the queue empties —
which is what makes "the pool returned to zero" a cost statement rather than a
tidiness one.

---

## 5. Guardrails

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Nothing below ~10<!--VD28--> % is readable | two identical points differed by 10<!--VD28--> % | §3.1 repeat row | — |
| Do not size above pool ceiling 8<!--VR8--> | the grid never reached saturation | §3.5 | — |
| The per-unit costs are latencies, not CPU | tier service time flat under 394<!--VD27--> % more load | §3.5 | `scripts/cluster/*.py` `burn()` |
| Rates come from the drain, not the window | 13.7<!--VD35--> vs 20.1<!--VD9--> units/s for the same point | `execution.md` §4 | `scripts/point.py` records both |
| `M4` counts scrape targets and is absent at both ends | fewer samples than every other ref, in every export | `execution.md` §1 register | `metrics.yaml` |
| Validity metrics must outlive the pods | the pool scales to zero and takes `/metrics` with it | `execution.md` §1 | `scripts/cluster/exporter.py`, Redis counters |

---

## 6. Reliability Economics

Out of scope, with one thing actually exercised.

Not exercised: node autoscaling, instance interruption, and the distinction
between an involuntary node loss and ordinary consolidation — the logic that
decides whether a real jobs point counts. kind has fixed nodes; none of it
runs.

Exercised: **work conservation across scale-in.** The pool goes from 8<!--VR8--> to 0 at
the end of every point, and `G1` checks that every unit enqueued was completed
exactly once. It held in all ten runs, which is a statement about the worker's
30-second grace period against a 0.25-second unit — not a claim that work
survives an instance being taken away, which is a different event that never
happened here.

---

## 7. Levers Evaluated

| Lever | Effort | Δ Drain | Δ Cost | Quality / risk price | Decision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Raise the pool ceiling past 8<!--VR8--> | trivial | unknown — still climbing at 8<!--VR8--> | more workers at peak | none identified | **not evaluated** — the rig would be the constraint, not the system |
| Raise the shared tier's ceiling | trivial | **none** | more replicas at peak | none | **rejected** — §3.5, the tier was never binding |
| Cut the autoscaler's ramp (`pollingInterval`, scale-up policy) | small | up to a third of a short drain | more API traffic | over-eager scale-out on a transient queue | **not evaluated** — named by §3.5 as one of two candidates |
| Scale unit count with the pool ceiling | small | — (changes what is measured) | none | the grid stops measuring identical work | **not evaluated** — it is the next execution |

The first pass of this execution is itself a lever evaluation that came out
negative: raising the shared tier's ceiling mid-grid *looked* like a 25<!--VD36--> %
improvement and moved nothing. It is in `execution.md` §3 as run #05, and the
reason it is kept is that the headline was convincing and wrong.
