> Draft of a GitHub comment to post on gastownhall/gastown#3768.
> Tone is "outsider offering reviewable work" -- humble about the fact that
> this is unverified against the gastown tree, concrete about what was
> actually done.

---

I built a formal model of this bug and a proposed fix, in case the structured
analysis is useful before the patch lands.

**Setup.** Kinner-modeled `sling.go:912-918` (lock acquire -> hookBeadWithRetry)
plus a `HookedSingleton` invariant: no two beads of the same `(assignee,
formula)` tuple may be in `hooked` status simultaneously. Three beads (two
sharing a formula, one cross-formula control), three slings contending for
the per-assignee lock, multi-cycle substrate.

**Bug verified.** TLC violates `HookedSingleton` at depth 28; 200/200 random
Python simulations reproduce the same shape (#3768's N=3+ accumulation).
Cross-formula bead stays clean -- the violation fires precisely on the
same-formula pair. The lock serializes the slings but doesn't prevent the
violation, demonstrating that the per-assignee lock is necessary but not
sufficient for the singleton-by-formula contract.

**Fix proposed and verified.** Insert `bd.CloseSameFormulaHooked(assignee,
formula)` between the lock acquire and `hookBeadWithRetry`. The fix model
explores 102,465 distinct states with both safety AND liveness clean; 0/200
random Python runs violate.

**Patch.** PR-ready Go in
[`proposed-patch/`](https://github.com/RunTheModel/gas-town-model/tree/main/proposed-patch)
of an external repo:
- New file `internal/beads/beads_sling_singleton.go`: ~80 lines,
  `(*Beads).CloseSameFormulaHookedSiblings`. Uses only existing public Beads
  APIs (`List`, `CloseWithReason`, `ParseAttachmentFields`, `IsProtectedBead`,
  `IssueStatusHooked`).
- 8 test cases in `internal/beads/beads_sling_singleton_test.go` (no-op, single
  close, multi close, leave-different-formula, leave-different-assignee,
  skip-protected, empty formula, empty assignee).
- Unified diff for `internal/cmd/sling.go` inserting the call (+22, -0).

The patch hasn't been compiled or tested against the gastown tree -- I don't
have a working gastown checkout. The function uses only existing public APIs
and matches the existing `bd := beads.New(workDir)` pattern at
`cmd/sling_helpers.go:162`. Three open questions for the maintainer are listed
in the patch [README](https://github.com/RunTheModel/gas-town-model/blob/main/proposed-patch/README.md).

**Other artifacts.** Bug/fix Kinner specs, TLC results, the 200-seed Python
simulation harness, and the
[modeling story](https://github.com/RunTheModel/gas-town-model/blob/main/sling-3768-story.md)
(three iterations of "find a deeper issue each time" before reaching the
liveness-clean fix) are all at the same external repo. The story is the most
interesting artifact in my opinion -- it shows how the formal verification
caught design issues that quick-glance review wouldn't have.

Happy to pair on review, adjust the patch to local conventions, or rewrite
the audit-reason format. The Kinner work is independent of the Go patch -- if
the maintainer wants to write the patch differently, the spec verification
still backs the design.
