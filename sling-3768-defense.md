# sling-3768 model: defense notes

Status: filed 2026-04-27. The bug demo at `sling-3768-bug.kinner.json`
TLC-violates `HookedSingleton`. This doc enumerates what someone could
challenge about that model, what the defense looks like, and the
ordered work to make it bulletproof.

The bug demo as it stands is sufficient to *show the violation*. It
is not yet defensible against scrutiny by someone who knows the
gastown code (Steve, witness, refinery authors). Don't ship the
model upstream without addressing P1 below.

## What the model claims

Issue #3768: `gt sling <formula> <agent>` does not check whether the
target agent already has a hooked molecule of the same formula.
Restarted/handed-off agents accumulate hooked patrol mols (one per
spawn or handoff event).

The spec at `sling-3768-bug.kinner.json` composes the substrate
spec (substrate.kinner.json) with two Bead instances and a Sling
that does what `internal/cmd/sling.go:912-918` does: acquire
per-assignee lock, call `hookBeadWithRetry`, no precondition check.
TLC produces a 19-step trace where BeadOld stays Hooked from t=0,
the patrol re-slings BeadNew on substrate Resumed, and the singleton
invariant violates.

## Known weaknesses

Ranked by how badly each would hurt under challenge.

### P1 — necessary to defend [SHIPPED 2026-04-28]

P1.1, P1.2, P1.3 all landed. TLC reproduces the violation at depth 29
(was 19 in v0.1) with the lock handshake observable in the trace and
both Slings using the AssigneeLock. Files added:
- `lib/assigneelock.kinner.json` (P1.2)
- `lib/priorpatrol.kinner.json` (P1.3)
- `lib/sling.kinner.json` v0.2 (P1.2 -- 5-state lock handshake)

`lib/priorsling.kinner.json` retired (replaced by `Sling` instance + `PriorPatrol`).

The original P1 critique below is preserved for context.

#### 1. Sling.HOOK_OUT fans out to both Beads

Real `hookBeadWithRetry` (sling.go:918) targets one specific bead row
by its `beadID`. There is no "all beads in this category receive a
message" broadcast. My model binds both `BeadOld.HOOK` and
`BeadNew.HOOK` to `Sl.HOOK_OUT`, relying on BeadOld's guard
(`status == 0`) to ignore the message. The result: the channel from
Sling to BeadOld sits InFlight forever -- a model artifact, not a
real-world condition.

Risk: a challenger says "your TLC trace might be exploring a state
space wider than the real system" and that's fair. The fan-out
introduces nondeterminism (which Bead's guard accepts) that
sling.go does not have.

Fix: add a `NeverFires` stub component (1-state, no triples, one
out-port that's never sent). Bind `BeadOld.HOOK` to
`NeverFires.OUT`. Sling targets only BeadNew via direct point-to-
point binding. Now sling.go:918's "target one specific bead-ID"
maps to the spec exactly.

#### 2. Per-assignee lock is named but not modeled

Sling has states `Idle -> LockHeld -> Done` but there's no
`AssigneeLock` actor and no second Sling to contend with it. The
lock is decorative. The issue body acknowledges the lock is not
the bug ("the singleton-by-formula contract is not enforced at the
sling boundary" -- the lock serializes, but serialization without
a check still produces the bug). But not modeling the lock leaves
room for "you don't even know it's irrelevant."

Fix: add `AssigneeLock` actor (Free / Held). Add a second
Patrol+Sling pair (or one Patrol that fires twice) so two slings
contend. Demonstrate: the lock serializes them; the bug still
shows up. Now we've shown the lock isn't the answer.

#### 3. Initial state bakes in the prior sling

BeadOld starts at `status=1` (Hooked) via the 148 `initial` option.
That's shorthand for "a prior sling happened before t=0." The
trace starts with one bead already in Hooked status without
showing how it got there.

Risk: a challenger says "you skipped showing the first sling. The
model only proves that *given* a Hooked bead, a second sling adds
another. It doesn't prove the system reaches that initial state via
a sling-go path."

Fix: add a `PriorSling` actor that fires once at t=0, transitioning
BeadOld from Open (0) to Hooked (1). Both slings are now observable
events in the trace. No baking initial state.

### P2 — rigor

#### 4. The bug report shows N=3+ accumulations; my model shows N=2 in one cycle [P2.4 SHIPPED 2026-04-28]

Substrate now loops maxCycles=2 times. All 5 substrate components
(Hook, Agent, HandoffCycle, Mailbox, Pane) loop. Hook uses a 134-shape
typed `cycleCount` variable. Patrols are loosely coupled -- they fire
on observed Resumed regardless of which cycle it is, and TLC explores
all interleavings.

Files: `lib/hook.kinner.json` v0.2 (counter + loop guard), updated
`lib/{agent,handoffcycle,mailbox,pane}.kinner.json` to loop. The
project drops the prior-bead bake-in entirely -- multi-cycle subsumes
P1.3's framing.

Crucially, the looseness is honest: in real gas-town, Hook fires on
context-window pressure, not on patrol or substrate state. The model
preserves that, so TLC explores realistic interleavings (some have
both patrols firing in cycle 1, some spread across cycles, some have
patrols missing the window entirely). The bug holds across every
interleaving where both patrols fire. Verified at depth 30, ~5685
distinct states, ~3 seconds.

For N>2 cycles (matching the bug report's "3+"), add another lane
(Patrol+Sling+Bead) and bump maxCycles. AssigneeLock currently has 2
client ports; add a third for N=3.

#### 4 (original critique). The bug report shows N=3+ accumulations; my model shows N=2 in one cycle

The reproduction in #3768 lists three hooked mol-deacon-patrol
beads (160min / 278min / 1317min old) -- one per substrate
respawn. My model demonstrates the *capability* to accumulate
(1 -> 2 in one cycle). It does not demonstrate the rate or
unboundedness.

Fix: revise `substrate.kinner.json` to support multiple cycles.
Resumed loops back to Active. Add `cycleCount: 0..maxCycles`
typed variable (134/148-shape). Patrol fires per cycle. With
`maxCycles=3`, the trace shows three accumulation events in
sequence. Matches the bug report.

#### 5. Formula identity isn't explicit [P2.5 SHIPPED 2026-04-28]

Bead v0.4 carries a `formula` typed-int variable initialized from a
148-shape `formulaId` option. The project now has three Bead lanes:
Bead1 (formulaId=1), Bead2 (formulaId=1), Bead3 (formulaId=2).
HookedSingleton became pairwise formula-keyed -- "no two beads of the
same formula are simultaneously Hooked."

Cross-formula sanity verified: a temporary variant with all three
beads at distinct formulas (1, 2, 3) explores the full state space
without violation. The bug variant (Bead1 and Bead2 sharing
formulaId=1) violates exactly on the same-formula pair, with Bead3
acting as a control that doesn't contribute to the violation.

AssigneeLock v0.2 extended to 3 clients to support the third Sling.
maxCycles bumped to 3 so each Patrol can land in its own cycle in
some interleavings (loose coupling per P2.4).

#### 5 (original critique). Formula identity isn't explicit

The two Beads are not tagged "same formula." I assert they are by
interpretation. A skeptic could say: "you have two Hooked beads,
sure, but were they the SAME formula? The singleton invariant is
PER-formula. Maybe sling targeted different formulas and the
singleton invariant doesn't apply."

Fix: add a `formula` typed-int variable to Bead (1 or 2). Two
same-formula Beads + one different-formula Bead. Singleton
invariant: at most one Hooked bead PER formula. Demonstrates the
bug is formula-keyed.

### P3 — disclosure [SHIPPED 2026-04-28]

Both P3.6 (counter-example reading guide) and P3.7 (fairness assumptions)
landed as a header section in the project description of
`sling-3768-bug.kinner.json`. Anyone reading a TLC counterexample now has
the variable->state mapping (status=0/1/2 -> Open/Hooked/Closed,
agentState/paneState/mailboxState/hookState/lockState semantics) plus the
fairness scope ("processes don't permanently stall; failure modes like
daemon-dead are out of scope").

#### 6 (original critique). typed-int over named states means traces show `status=1` instead of `status=Hooked`

Less self-documenting counter-examples. Reader has to know the
mapping.

Fix: add a header comment on the project file: "status=0/1/2 in
counter-example traces correspond to Open/Hooked/Closed in
internal/beads/status.go." Reader has the mapping.

(Or: Kinner language feature -- per-instance initialState. But
that's a separate ask.)

#### 7. Substrate fairness on every component

Weak fairness models "these processes don't permanently stall."
Some realistic failure modes (daemon dead, no respawn ever) violate
this. Not the bug we're modeling, but worth disclosing.

Fix: add a header comment: "weak fairness on every component
models 'these processes don't permanently stall.' Specs that assume
otherwise (daemon dead, no respawn) are out of scope for this
model."

## Defense plan, ordered

1. **P1 work (60-90 min)**: split fan-out, add AssigneeLock with
   contending Slings, model PriorSling explicitly.
2. **P2 work (60-90 min)**: multi-cycle substrate, formula
   identity. Requires revising `substrate.kinner.json` (which
   currently models one cycle).
3. **P3 work (15 min)**: disclosure comments in the project header.

Total to be defensible against Steve-level scrutiny: ~3 hours of
focused work.

## Interim posture (do this even before P1)

Before any of the above, append a "Limitations" section to the
project's `description` field listing every gap above. This
converts unknown-unknowns into disclosed-knowns. A challenger who
points at fan-out gets: "yes, see Limitations item 1 -- known
shortcut." Defensible even with the current model. Does not make
the model bulletproof; does prevent looking surprised when
challenged.

## Files

- `sling-3768-bug.kinner.json` -- the project spec
- `lib/bead.kinner.json` -- bead lifecycle (typed-int status, 148 init)
- `lib/sling.kinner.json` -- gt sling subcommand (lock + hookBeadWithRetry)
- `lib/patrol.kinner.json` -- witness/refinery patrol scheduler
- `substrate.kinner.json` + `lib/{agent,handoffcycle,mailbox,pane}.kinner.json`
  -- the substrate spec (one cycle as of v0.1)

## What done looks like

A re-runnable TLC pipeline that:
1. Verifies the substrate spec by itself (3-state Agent cycle, mail
   safety, liveness).
2. Verifies the multi-cycle bug spec (P1+P2 above) and produces a
   trace showing N>=3 hooked beads of the same formula at the same
   agent.
3. Verifies a fix spec where a `CloseOldHooks` actor sweeps existing
   hooked beads of the same formula before each Patrol re-sling, and
   the singleton invariant holds.

The fix model is the natural next step after defense work; it's
where we *demonstrate* the proposed sling.go change, rather than
just argue for it.
