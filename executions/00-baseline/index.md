# Execution · 00 · Baseline

| | |
| :--- | :--- |
| Produces | this document — the givens every other execution inherits, plus the floor |
| Preconditions | none — this is the first thing that happens |
| Data | `./data/` — constants, dated in the filename |
| Scripts | `./scripts/` — profilers and one-off capture |
| Optional | `./metrics.md` — move §1's metric tables there when this file gets long |
| Status | ⟨planned · running · closed⟩ |

> **Ownership rule — nothing in §1–§6 is the subject of a measurement.** Everything here
> is a given: components, versions, models, frozen configuration, the input fixture, the
> rate card. Other executions cite these sections; they never restate them.
>
> If a value here becomes an axis, **it leaves this document** and becomes that execution's
> input. The winner returns here in the next revision.
>
> Worked example: `bge-mini-v3` is the embedding model — a given, recorded in §1, not a
> finding. The moment an execution named *"bge-mini-v3 versus alternatives"* exists, the
> model becomes that execution's axis and is struck from here until it is decided again.
>
> The test is not "is it shared" but **"is it under test"**.

---

# 1 · Components

One block per component. Configuration and exposed metrics live together, so adding a
component touches one place.

### ⟨Component name⟩

| | |
| :--- | :--- |
| Version / identity | ⟨image, chart, model, commit⟩ |
| Placement | ⟨where it runs⟩ |
| Resources | ⟨requests / limits / sizing⟩ |
| Elasticity | ⟨scales on ⟨signal⟩ · floor ⟨n⟩ · ceiling ⟨n⟩ — or: fixed⟩ |

**Observable** — names read off the live endpoint, not from documentation. A wrong name
returns no data and is indistinguishable from a missing target.

| Ref | Metric | Name as exposed | Status |
| :--- | :--- | :--- | :--- |
| E⟨n⟩ | ⟨what it measures⟩ | `⟨name⟩` | ⟨available · pending · retired in v⟨n⟩⟩ |

⟨Notes: behaviour recorded but deliberately not fixed, because changing it mid-measurement
would destroy comparability. State the expected effect and the candidate change for the
next revision.⟩

### Metric register

Map of ranges. Numbers are permanent: a retired metric keeps its ref and gains a status, so
references in older revisions stay resolvable. Never renumber, never reuse.

| Range | Component / domain | Added |
| :--- | :--- | :--- |
| E1–E9 | ⟨cost and capacity — nodes, queues, egress⟩ | v1.0 |
| E10–E19 | ⟨component⟩ | v1.0 |
| E20– | *reserved* | |

> **Executions reference these; they do not redefine them.** Which metrics a run reads,
> with what filters, and what each one gates is method — it lives in that execution's
> Instrumentation section.

**Filtering that is mandatory, not cosmetic:** ⟨any metric mixing several producers that
cannot be split after the fact⟩

**Deliberately not observable:** ⟨what, and why it is not needed⟩

### Elasticity summary

Which components can reach zero and which cannot. This table decides whether any claim
about elastic cost survives contact with a bill.

| Component | Scales on | Floor | Ceiling |
| :--- | :--- | :--- | :--- |
| | | | |

⟨Consequences: which capacity is permanent; which is shared between paths and therefore
cannot be attributed to one of them; whether the observability stack is itself part of the
system rather than only the instrument.⟩

---

# 2 · Configuration freeze

Decided once, before the first run. Changing any of these invalidates comparability;
changing them between executions means a new revision of this document.

| Parameter | Value | Why it must be frozen |
| :--- | :--- | :--- |
| | | |

Frozen by ⟨⟩ · Date ⟨⟩ · Commit ⟨⟩

> Include anything that would silently change the shape of a result — sizing, placement,
> packing density, background maintenance behaviour. A parameter left free is a parameter
> that will differ between points.

---

# 3 · Input fixture

> **Yields:** the denominator of every unit-cost figure.
> **From:** `./scripts/⟨profiler⟩` → `./data/⟨name⟩-profile.txt`
> **Before any run:** profile first, then freeze. An input that changes between points
> makes every result matrix meaningless.

| | |
| :--- | :--- |
| Source | |
| Snapshot location | |
| **Exact unit count** | ← the denominator |
| Distribution — median · p95 · total | |
| Size | |
| Freeze date | |

*How to read a distribution: the median is the typical case — half is smaller. The 95th
percentile is the tail, and the tail drives worst-case resource use and time.*

**One denominator, not two.** A second unit doubles every table for a conversion the reader
can perform from the distribution above.

---

# 4 · Price basis

> **Before any run:** unrecoverable afterwards. Rates change, and an undated basis makes
> every derived figure unverifiable.

- [ ] ⟨every rate any figure will use — including ones only later executions need⟩

Date captured: ⟨⟩ → `./data/price-⟨YYYY-MM-DD⟩.⟨ext⟩`

**Run cost is computed from this, never read from a bill.** Billing aggregates on a daily
cycle and cannot see a short run at all. Billing exports are used for the idle window only.

---

# 5 · Floor — cost at zero load

> **From:** the idle window in §7.4.
> **Before the run:** attribution live and activated; zero activity for the full window.

Split rather than totalled: for anything claiming elastic economics, the floor is the whole
argument, and it is where published architectures are least honest.

| Block | What it is | ⟨$/month⟩ |
| :--- | :--- | :--- |
| A | shared — exists without this subject | |
| **B** | **dedicated — disappears with it. The headline** | |
| C | standalone — A + B | |

⟨Line-by-line breakdown of A and B, each classified fixed vs variable. Close with the notes
this table exists for: lines billed regardless of traffic, lines billed per unit of data
moved, and the qualification of any prior public claim about idle cost.⟩

---

# 6 · Envelope

Conditions under which every figure downstream holds. Each execution adds its own on top.

> ⟨On what system, at what scale, against what input, in what environment. Outside these
> conditions, re-measure.⟩

Deliberately outside it: ⟨⟩

---

# 7 · How this was established

The working record. Nothing below is cited by other executions.

## 7.1 Cost attribution

Not retroactive. Longest lead time of anything here — do it first.

- [ ] Tags or labels applied at the source of truth (IaC, not the console)
- [ ] Rolled out — every component carries the right value
- [ ] **Activated** where activation is a separate step from tagging
- [ ] Verified on a live resource, not in plan output

Date attribution went live: ⟨⟩

> Without this, cost reporting returns one undifferentiated number and the floor cannot be
> split. It is the most common reason a cost report is impossible rather than merely late.

## 7.2 Observability verification

Verified by query, not by reading config.

**Required before any execution:**

- [ ] No scrape target down
- [ ] ⟨refs⟩ return data, with the filters the executions will actually use
- [ ] Anything the system under test itself depends on for correct behaviour — if the
  observability stack drives autoscaling or alerting, it is part of the system, not only
  the instrument

**Optional — gates ⟨specific claim⟩ only. Not a gate for the runs:**

- [ ] ⟨refs⟩

> A component that is not observed cannot be named as a constraint, because an absent
> series looks exactly like an idle one. But an optional metric blocks one claim, not the
> whole report — say which claim, and start without it if it is late.

**Confirmed names.** Read each off the live endpoint, then write it into the component
block in §1.

| Ref | Component | Name as exposed | Copied to §1 |
| :--- | :--- | :--- | :--- |
| | | | |

## 7.3 Constants captured → `./data/`

Dated in the filename. Re-capturing later means a new file, never an overwrite.

- [ ] **Prices** → `./data/price-⟨date⟩.⟨ext⟩` — every rate any figure will use. Dating two
  snapshots costs more than taking one complete one.
- [ ] **Fixture profile** → `./data/⟨name⟩-profile.txt`
- [ ] **System configuration snapshot** → `./data/⟨name⟩-config.json`
- [ ] **Artifact identity** → `./data/⟨name⟩-identity.json`

## 7.4 Idle window → §5

- [ ] Scheduled so that **no execution point falls inside it**. One point inside destroys
  the window
- [ ] Zero workload and zero human activity for the full window: no deploys, no config
  changes, no manual commands. Automated reconciliation stays on — it is part of the floor
- [ ] Window spans a full daily cycle: backups, rotations, scheduled jobs

Window UTC: start ⟨⟩ → end ⟨⟩

Audit every always-billed line explicitly, and mark ᴬ anything computed from §4 rather than
resolved from the bill. The lines most often missed are those billed by the hour regardless
of traffic, and those billed per unit of data moved.

## 7.5 Open verification

Facts that must be confirmed rather than assumed, because a wrong assumption fails silently
rather than loudly.

| Item | What it invalidates if wrong | Resolved |
| :--- | :--- | :--- |
| | | |

## 7.6 Gate

- [ ] §7.1 green — attribution live, date recorded
- [ ] §7.2 required rows green
- [ ] §2 frozen
- [ ] §7.3 constants captured and dated
- [ ] §7.4 window closed and floor split into §5
- [ ] §7.5 resolved
- [ ] Tooling configured and dry-run clean

Date: ⟨⟩ · Optional items still open, and which claim each puts at risk: ⟨⟩

---

# 8 · Teardown artifacts

Captured after the final execution, **before** anything is destroyed.

- [ ] ⟨artifact⟩ → ⟨location⟩ · checksum ⟨⟩
- [ ] Manifest alongside it: versions, parameters, identity of everything that produced it

*Why nothing else produces it:* ⟨cost of regenerating from scratch⟩
