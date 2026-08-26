# Execution · ⟨NN-name⟩ — Concepts

> **Optional file.** The hard parts of this execution, in plain words. Create it when
> explanations start crowding out values in `index.md`. Read by the author a year later and
> by whoever writes the next revision — never by the operator during a run.

**`index.md` states values. This file explains mechanisms.** No instance type, threshold,
count or date appears below; those live in `index.md`, cited by section and never copied.
The two files do not overlap by construction, which is what stops them drifting apart.

**Scope test:** would this explanation still be true on a different project, input and
platform? Yes → it is a kit rule, cite `methodology.md` in one line and stop. No → here.

**What earns an entry:** a term an engineer outside this project would not know · a number
that follows from two other numbers and was never chosen directly · a mechanism where the
obvious action is the wrong one · a boundary that fails silently instead of loudly.
**Anything that fits in one table cell stays in that cell.**

---

## Register

Refs are permanent. A concept that stops applying keeps its ref and gains a status, so links
from older revisions still resolve. Never renumber, never reuse.

| Ref | Concept | Cited from | Status |
| :--- | :--- | :--- | :--- |
| M⟨n⟩ | ⟨three or four words⟩ | §⟨n⟩ | ⟨active · superseded by M⟨n⟩ · retired in v⟨n⟩⟩ |

> **M refs are execution-local**, like C and R. Cited from outside with their execution:
> `00-baseline M3`. Only E refs are global, because only E refs are properties of the system.

---

## M⟨n⟩ · ⟨concept⟩

**One line:** ⟨what it is, for a reader who has never seen this system⟩

⟨One to three paragraphs. Plain language, no term used before it is defined. What the thing
is, what produces it, and why the obvious reading of it is wrong. Written as if to a
competent engineer who joined this week.⟩

**Consequence:** ⟨what breaks if the value behind this changes — which figure, which
section, which claim dies⟩

> **Consequence is the line that cannot be reconstructed later.** Why something is the way it
> is stays recoverable from the logic a year on; what silently breaks if you touch it does
> not, and its absence is how a later revision removes a constraint without noticing.
