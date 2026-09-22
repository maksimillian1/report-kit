# Executive Engineering Report — queue drain (example)

> **This is the kit's worked example for the jobs profile, not a real report.**
> Every figure comes from a real run on a single-node local cluster — see
> `execution.md` and the files under `scripts/data/`. Nothing here is
> fabricated, which is why the cost sections are empty: a laptop has no price
> basis, and inventing one would teach exactly the wrong lesson.

Legend — ᴰ derived · ᴱ estimated · ᴿ recorded during the run · ᴱˣ excluded

---

## Coverage

| Area | Status | Evidence | Cost of absence | Since |
| :--- | :--- | :--- | :--- | :--- |
| Drain time vs worker pool ceiling | measured | `execution.md` §4 | — | v1 |
| Whether the shared tier is the constraint | **measured, and it is not** | `execution.md` §4, refs D10 / M6 | — | v1 |
| Where the pool's saturation point is | **not found** | `execution.md` §4 Saturation | the grid ends before the system does; sizing above `n = 8` is unsupported | v1 |
| Ramp vs contention above `n = 4` | **declared, not separated** | `execution.md` §4 | the missing 30<!--FD17--> % of per-worker efficiency has two candidate causes and no verdict | v1 |
| Cost per unit drained | **declared, not measured** | — | no price basis exists for a local cluster | v1 |
| Behaviour under worker loss | **out of scope** | — | a pod killed mid-unit would be caught by `G1`; it never happened, so nothing is claimed | v1 |
| Node autoscaling and instance interruption | **out of scope** | — | kind cannot create or reclaim nodes; the real jobs profile's validity logic stays untested | v1 |

---

## 1. BLUF

Raising the worker pool ceiling from 1<!--FR5--> to 8<!--FR8--> cuts the drain
of 1,200<!--FR1--> units from **284<!--FM1--> s to 50<!--FM4--> s** — a
5.6<!--FD4-->× speed-up for 8<!--FR8-->× the workers, with per-worker
efficiency falling from 100<!--FD6--> % to 70<!--FD9--> %.

**No ceiling was found**, and the component predicted to be the ceiling is
provably not one: the shared tier ran pinned at its own replica maximum
through every point while its service time moved 17<!--FD11--> % against a
464<!--FD12--> % rise in throughput. Adding workers was still buying throughput where this grid stops.

**The prediction failed because it priced the wrong resource.** The tier costs
60<!--FR4--> ms of wall time per unit, not 60<!--FR4--> ms of exclusive CPU — a
latency, not a capacity. That distinction is the transferable finding here; the drain numbers
belong to one laptop.

---

## 2. Workload Contract & Envelope

One unit is one queue message: 150<!--FR3--> ms of worker time, then one call
to the shared tier costing 60<!--FR4--> ms of its time. One unit in twenty fails after the burn
and is requeued exactly once — **deterministically**, so that every point on
the grid does identical work.

Arrivals are offered at a **constant rate** (40<!--FR2--> units/s), open model, and the
producer runs concurrently with the measurement. A producer paced by the drain
could not build a backlog, and the backlog is the thing under test.

| | |
| :--- | :--- |
| Envelope | worker pool 0–8, `600m` CPU limit each; shared tier 1–2 replicas at `500m` |
| Unit cost of work | 150<!--FR3--> ms worker + 60<!--FR4--> ms shared tier, both wall-clock |
| Measured range | pool ceiling 1<!--FR5--> – 8<!--FR8-->, 1,200<!--FR1--> units per point, 40<!--FR2--> units/s offered |
| Not covered | pool ceilings above 8, unit counts scaled per point, a non-deterministic failure share, sustained arrival rates above the drain rate |

---

## 3. Efficiency Frontier

### 3.1 Run matrix

| Pool ceiling | D8 drain | D9 units/s | Speed-up | Per-worker efficiency | D10 tier service | Saturation signal |
| ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 1<!--FR5--> | 283.7<!--FM1--> s | 4.23<!--FM6--> | 1.00<!--FD1-->× | 100<!--FD6--> % | 72.0<!--FM11--> ms | baseline ᴿ |
| 2<!--FR6--> | 146.7<!--FM2--> s | 8.18<!--FM7--> | 1.93<!--FD2-->× | 97<!--FD7--> % | 72.5<!--FM12--> ms | near-linear ᴿ |
| 4<!--FR7--> | 84.4<!--FM3--> s | 14.22<!--FM8--> | 3.36<!--FD3-->× | 84<!--FD8--> % | 81.1<!--FM13--> ms | efficiency decaying ᴿ |
| 8<!--FR8--> | 50.3<!--FM4--> s | 23.85<!--FM9--> | 5.64<!--FD4-->× | 70<!--FD9--> % | 83.4<!--FM14--> ms | still climbing ᴿ |
| 8<!--FR8--> (repeat) | 53.3<!--FM5--> s | 22.51<!--FM10--> | 5.32<!--FD5-->× | 67<!--FD10--> % | 84.2<!--FM15--> ms | ±6<!--FD13--> % on the same point ᴿ |

A five-point first pass at 400<!--FR9--> units per point is excluded: its drains were
short enough that the autoscaler's ramp was most of the measurement. See
`execution.md` §3 note #05 — it is the most instructive row in this example.

### 3.2 Chart

Not rendered — the example has no charting step. In a real report this is
where drain time and per-worker efficiency would be drawn against pool
ceiling on one pair of axes, because the finding is that they diverge: the
first keeps improving while the second is already falling.

### 3.3 Knee · sweet spot · waste boundary

| | Pool ceiling | Read from |
| :--- | ---: | :--- |
| **Sweet spot** | 2<!--FR6--> | 97<!--FD7--> % per-worker efficiency, still essentially linear |
| **Knee** | between 2<!--FR6--> and 4<!--FR7--> | efficiency drops 13<!--FD16--> points across this interval |
| **Throughput peak** | **not reached** | still climbing at 8<!--FR8-->, which is where the rig stops |
| **Waste boundary** | not established | needs a grid that reaches saturation |

The sweet spot is where a worker is still worth what it costs, not where the
queue drains fastest. Those are different rows, and on this grid they are at
opposite ends of it.

### 3.4 Shape of the cost curve

Per-worker efficiency decays from the second point onward — there is no flat
region where workers are free. What the grid does not show is a *turn*:
efficiency is falling smoothly and throughput is still rising, so nothing here
identifies a rate beyond which adding workers stops paying, only a rate beyond
which each one pays less.

### 3.5 Constraint ladder

**No tier is proven, and the one that was expected is ruled out.**

The shared tier was built to be the first ceiling: capped at two replicas,
60<!--FR4--> ms per call, sized to cap throughput near 16.7<!--FE1--> units/s.
It did not. It sat at its replica maximum (`M6 = 2`) in every point while
throughput reached 23.9<!--FM9--> units/s, and its own service time (`D10`)
rose 17<!--FD11--> % against a 464<!--FD12--> % rise in load. A tier being *relieved* is what proves the tier below it; this one was
never binding, so there is nothing to relieve.

**Two candidates remain for the decaying efficiency, and this grid separates
neither**: the autoscaler's ramp, which is 15–30 s of a 50<!--FM4--> s drain at the top
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
seconds. A drain that is 5.6<!--FD4-->× faster on 8<!--FR8-->× the workers costs more per unit,
not less, unless the instances are reclaimed the moment the queue empties —
which is what makes "the pool returned to zero" a cost statement rather than a
tidiness one.

---

## 5. Guardrails

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Nothing below ~6<!--FD13--> % is readable | two identical points differed by 6<!--FD13--> % | §3.1 repeat row | — |
| Do not size above pool ceiling 8<!--FR8--> | the grid never reached saturation | §3.5 | — |
| The per-unit costs are latencies, not CPU | tier service time flat under 464<!--FD12--> % more load | §3.5 | `scripts/cluster/*.py` `burn()` |
| Rates come from the drain, not the window | 14.2<!--FD18--> vs 23.9<!--FM9--> units/s for the same point | `execution.md` §4 | `scripts/point.py` records both |
| `M4` counts scrape targets and is absent at both ends | fewer samples than every other ref, in every export | `execution.md` §1 register | `scripts/series.txt` |
| Validity metrics must outlive the pods | the pool scales to zero and takes `/metrics` with it | `execution.md` §1 | `scripts/cluster/exporter.py`, Redis counters |

---

## 6. Reliability Economics

Out of scope, with one thing actually exercised.

Not exercised: node autoscaling, instance interruption, and the distinction
between an involuntary node loss and ordinary consolidation — the logic that
decides whether a real jobs point counts. kind has fixed nodes; none of it
runs.

Exercised: **work conservation across scale-in.** The pool goes from 8<!--FR8--> to 0 at
the end of every point, and `G1` checks that every unit enqueued was completed
exactly once. It held in all ten runs, which is a statement about the worker's
30-second grace period against a 0.25-second unit — not a claim that work
survives an instance being taken away, which is a different event that never
happened here.

---

## 7. Levers Evaluated

| Lever | Effort | Δ Drain | Δ Cost | Quality / risk price | Decision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Raise the pool ceiling past 8<!--FR8--> | trivial | unknown — still climbing at 8<!--FR8--> | more workers at peak | none identified | **not evaluated** — the rig would be the constraint, not the system |
| Raise the shared tier's ceiling | trivial | **none** | more replicas at peak | none | **rejected** — §3.5, the tier was never binding |
| Cut the autoscaler's ramp (`pollingInterval`, scale-up policy) | small | up to a third of a short drain | more API traffic | over-eager scale-out on a transient queue | **not evaluated** — named by §3.5 as one of two candidates |
| Scale unit count with the pool ceiling | small | — (changes what is measured) | none | the grid stops measuring identical work | **not evaluated** — it is the next execution |

The first pass of this execution is itself a lever evaluation that came out
negative: raising the shared tier's ceiling mid-grid *looked* like a 43<!--FD19--> %
improvement and moved nothing. It is in `execution.md` §3 as run #05, and the
reason it is kept is that the headline was convincing and wrong.
