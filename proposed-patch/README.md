# sling-3768 proposed patch

PR-ready Go patch for `gastownhall/gastown#3768`. Three pieces:

| File | Purpose | Status |
|---|---|---|
| `internal/beads/beads_sling_singleton.go` | New file: `(*Beads).CloseSameFormulaHookedSiblings` | Drafted, ~80 lines |
| `internal/beads/beads_sling_singleton_test.go` | Tests for the new function | Drafted, ~200 lines, 8 cases |
| `sling.go.patch` | Unified diff inserting the call between sling.go:916 and 917 | Drafted, +22 / -0 |

## How to apply

```bash
# from a gastown checkout root:
cp /path/to/proposed-patch/internal/beads/beads_sling_singleton.go internal/beads/
cp /path/to/proposed-patch/internal/beads/beads_sling_singleton_test.go internal/beads/
patch -p1 < /path/to/proposed-patch/sling.go.patch
go test ./internal/beads/... -run CloseSameFormula
go vet ./...
```

## What it does

`(*Beads).CloseSameFormulaHookedSiblings(assignee, formulaName)`:

1. Lists beads with `Status="hooked"` and `Assignee=assignee` (uses existing
   `b.List(ListOptions{...})`).
2. Filters to those whose parsed `attached_formula` matches `formulaName`
   (uses existing `ParseAttachmentFields(issue)`).
3. Skips protected beads (existing `IsProtectedBead(issue)` check covers
   `gt:keep`, `gt:standing-orders`, `gt:role`, `gt:rig`).
4. Closes the matching set with an audit reason citing #3768 (uses existing
   `b.CloseWithReason(reason, ids...)`).
5. Returns the closed IDs for logger output.

The sling.go diff calls it between the lock acquire and `hookBeadWithRetry`,
so the close-then-hook pair is atomic under the per-assignee lock.

## Confidence

**Design**: high. Verified by TLC across 102,465 reachable states with both
safety (HookedSingleton) and liveness checks. See `../sling-3768-fix.kinner.json`
and `../sling-3768-story.md` for the modeling work that produced this design.

**Patch**: moderate. The function uses only existing public Beads APIs
(`List`, `Show`, `CloseWithReason`, `ParseAttachmentFields`, `IsProtectedBead`,
`IssueStatusHooked`, `StatusClosed`). The patterns match those in the
existing codebase (e.g., `cmd/sling_helpers.go:162` uses the same
`bd := beads.New(workDir)` pattern). The patch has not been compiled or
tested against gastown's tree -- the maintainer should:

1. Confirm `townRoot` is the right `workDir` for `beads.New` at the call
   site (sling.go uses `beads.ResolveHookDir(townRoot, ...)` immediately
   after, so `townRoot` is in scope).
2. Verify the audit-reason assertion in the test file matches gastown's
   audit-log conventions (the assertion is currently a permissive log,
   expected to be tightened by the maintainer).
3. Run the gastown integration test suite.

## Test cases (in beads_sling_singleton_test.go)

| Test | What it proves |
|---|---|
| `TestCloseSameFormulaHookedSiblings_NoMatches` | Returns `(nil, nil)` on the common path (first sling for an (assignee, formula) pair) |
| `TestCloseSameFormulaHookedSiblings_ClosesSingle` | Closes one stale hooked bead, returns its ID |
| `TestCloseSameFormulaHookedSiblings_ClosesMultiple` | Closes multiple stale hooked beads atomically (matches the #3768 N=3 reproducer) |
| `TestCloseSameFormulaHookedSiblings_LeavesDifferentFormula` | Different-formula hooked beads on the same assignee are untouched -- the formula key works |
| `TestCloseSameFormulaHookedSiblings_LeavesDifferentAssignee` | Same-formula hooked beads on a different assignee are untouched -- the assignee key works |
| `TestCloseSameFormulaHookedSiblings_SkipsProtected` | gt:keep / gt:standing-orders beads survive -- pinning beats formula-singleton |
| `TestCloseSameFormulaHookedSiblings_EmptyFormulaName` | Plain (raw-bead) slings skip the singleton enforcement entirely |
| `TestCloseSameFormulaHookedSiblings_EmptyAssignee` | Defensive: empty assignee returns `(nil, nil)` without listing |

## Open questions for the gastown maintainer

1. **Where should `formulaName` come from on a re-sling that didn't pass it
   explicitly?** The patch only enforces the singleton when `formulaName != ""`.
   If a re-sling is invoked without `<formula>` (e.g., `gt sling --on <bead>`
   without a formula arg), the singleton isn't enforced. Per the bug shape
   in #3768 the re-slings DO carry the formula (`mol-deacon-patrol` etc.),
   so this is fine, but worth confirming.
2. **Should the close be unconditional or label-gated?** The patch skips
   protected beads. An alternate design closes them anyway and lets the
   protection labels surface in the close audit. The conservative choice
   is what the patch does; happy to flip if the maintainer prefers.
3. **Does the audit reason format need to match an existing convention?**
   The patch uses `"superseded by new sling for formula %q on %s (gastown #3768)"`.
   Adjust to match local audit-log style.

## Verification done before this patch

The Kinner specs at `../sling-3768-bug.kinner.json` (bug demo) and
`../sling-3768-fix.kinner.json` (fix proof) provide formal evidence:

- TLC explores 102,465 distinct states for the fix; **safety AND liveness
  hold** with no counterexample
- Random Python simulation (200 seeds, 10000 steps each) confirms: bug
  spec violates 200/200 (100%); fix spec violates 0/200

The full modeling story including three iterations of "find a deeper issue
each time" is at `../sling-3768-story.md`. The story is itself a useful
artifact -- it shows what kinds of bugs the formal verification catches
that quick-glance review wouldn't.
