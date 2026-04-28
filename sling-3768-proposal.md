# Issue #3768: Bug + proposed fix (one-pager)

## The bug

`gt sling <patrol-formula> <agent>` does not check whether the target agent
already has a hooked bead of the same formula. As a result, restarted /
handed-off agents accumulate multiple `mol-{deacon,witness,refinery}-patrol`
beads in `hooked` status -- one per (re)spawn. The bug report shows three
hooked patrol beads on a single deacon (160 / 278 / 1317 minutes old).

The per-assignee lock at `internal/cmd/sling.go:912` (`tryAcquireSlingAssigneeLock`)
serializes concurrent slings against the same agent but does **not** enforce the
singleton-by-formula contract. Each invocation just acquires the lock and
calls `hookBeadWithRetry` (line 918), unconditionally creating a new hooked
bead row.

## Evidence (formal)

A pair of Kinner specs (`sling-3768-bug.kinner.json`,
`sling-3768-fix.kinner.json`) verified by TLC and re-run as random Python
simulations:

| Spec | Safety (HookedSingleton) | Liveness | Python (200 random seeds) |
|---|---|---|---|
| Bug spec | TLC violates at depth 28 | n/a | 200/200 violations (100%) |
| Fix spec | clean across 102,465 states | passes | 0/200 violations |

`HookedSingleton` is the formula-keyed singleton: no two beads of the same
(assignee, formula) tuple may be in `hooked` status simultaneously. The bug
spec violates because nothing closes the existing hooked bead before the
re-sling. The fix spec adds a precondition close-step and the violation
becomes unreachable.

Models cite real source: `sling.go:912` (assignee lock), `sling.go:918`
(`hookBeadWithRetry`), the witness/refinery patrol-cycle loops that drive
the re-sling.

## Proposed fix

Between the lock acquire (`sling.go:916`, immediately after the `defer
assigneeUnlock()`) and the `hookBeadWithRetry` call (line 918), close any
existing `hooked` beads on the same (assignee, formula) tuple:

```go
// sling.go, between current lines 916 and 917
if err := beads.CloseSameFormulaHooked(townRoot, targetAgent, formulaName); err != nil {
    return fmt.Errorf("closing existing same-formula hooks for %s: %w", targetAgent, err)
}
```

`CloseSameFormulaHooked(townRoot, assignee, formula)` is a new beads-package
function:

1. Lists beads where `assignee = ?` AND `formula = ?` AND `status = hooked`.
2. For each, transitions `status` to `closed` (the same path `gt done`
   uses).
3. Returns nil if zero or more existed; only errors on DB failure.

The function is idempotent: a no-op when there are no existing hooked
siblings (the common path on first sling).

## Why this works (and other approaches don't)

The per-assignee lock alone is necessary but not sufficient. The Kinner
fix model demonstrates lock contention between two simultaneous slings;
even with serialization, both end with their respective beads `hooked`
because neither sling closes the other's bead. The lock prevents
concurrent corruption; it doesn't enforce the formula singleton contract.

A receiver-side approach (have the bead self-close on observing a new
sling) was considered and rejected: beads don't observe slings; the
identity-by-formula check naturally lives on the writer side.

## PR readiness: what's done and what's needed

**Done:**
- Bug demonstrated formally (TLC + Python)
- Fix demonstrated formally (TLC + Python)
- The proposed code-level change is one new beads-package function plus
  one inserted call in `sling.go`
- Sling.go:912-918 reviewed; the call site matches the model

**Still needed for a Go PR:**
- Read `internal/beads/` to confirm the right query/update primitives
  (`status.go` already defines `StatusClosed = "closed"` and
  `IssueStatusHooked = "hooked"` typed constants -- the typed forms exist).
- Implement `CloseSameFormulaHooked` -- likely ~20-30 lines using existing
  beads-list and beads-update helpers
- Add a test in `internal/beads/status_test.go` covering: no-op on empty,
  closes single, closes multiple, leaves different-formula beads alone
- Add an integration test for `sling.go` covering the regression: invoke
  `gt sling` twice on the same (formula, agent), assert only one is
  `hooked` afterward
- Run gastown's test suite

**Confidence level**: high on the design, moderate on the patch. The
design is verified by TLC; the patch is mechanical but requires reading
the beads-package APIs to write idiomatic Go.

## Files

- `sling-3768-bug.kinner.json` -- bug demonstration spec
- `sling-3768-fix.kinner.json` -- proposed-fix verification spec
- `sling-3768-defense.md` -- defense notes (P1+P2+P3 critique pre-empted)
- `sling-3768-story.md` -- the modeling journey (three iterations to
  liveness-clean fix)
- `lib/slingwithcheck.kinner.json` -- the proposed `gt sling` flow as a
  Kinner component
- `lib/beadcloseable.kinner.json` -- bead lifecycle with close transition
