# gate-3587 model: defense notes

Status: filed 2026-04-29. The bug demo at `gate-3587-bug.kinner.json`
TLC-violates the `PolecatEventuallyWorking` liveness property at depth 8.
The fix demo at `gate-3587-fix.kinner.json` verifies clean across 37
distinct states. This doc enumerates what someone could challenge about
either model, what the defense looks like, and the ordered work to make
it bulletproof.

The pair as it stands is sufficient to *show the bug shape and the fix
shape*. It is not yet defensible against scrutiny by someone who knows
the gastown internals (Steve, the carlory who filed #3587, the prime
authors). Don't ship the model upstream without addressing P1 below.

## What the model claims

Issue #3587: if the Deacon session dies after `bd gate check` closes a
gate but before `gt gate wake <id>` runs, parked polecats never receive
their wake notification and wait indefinitely. The proposed fix is a
`checkParkedWork()` step in `gt prime` that self-heals by reading the
persisted parked-state and observing the gate.

The bug spec composes:
  - Polecat (extended with Parked/PARK_IN/WAKE_IN)
  - Issue (decorative; satisfies Polecat's ISSUE_OBSERVE binding)
  - Parker (one-shot, puts Polecat into Parked at t=0)
  - Gate (Open / Closed)
  - Deacon (5-state protocol: Idle -> ClosingGate -> WakeReady -> Done,
    with an explicit WakeReady -> Crashed transition)
  - NeverFires stubs for Polecat's unused work-coordination ports

TLC produces a counterexample in 8 steps: Deacon closes gate, observes
Closed, transitions WakeReady -> Crashed; Polecat stays Parked forever;
liveness fails.

The fix spec adds PrimeRecovery (observes Polecat=Parked AND Gate=Closed,
sends Wake on satisfaction). 102k... actually 37 distinct states, all
reachable behaviors satisfy the liveness property.

## Known weaknesses

Ranked by how badly each would hurt under challenge.

### P1 — necessary to defend

#### 1. Crash is an actor-internal transition, not an external event

Real sessions die from SIGTERM (tmux pane closed), OOM, parent process
death, panic, etc. -- all *external* causes. The model puts the
WakeReady -> Crashed branch as one of Deacon's normal state-machine
transitions, which TLC treats as an internal nondeterministic choice.
A reviewer could say "your model lets Deacon 'decide' to crash, which
isn't faithful to how processes actually die."

The functional behavior is the same -- TLC explores both the
crashed-branch and the proceed-branch, and the bug shape is reachable.
But the framing is wrong on the surface.

Fix: model the crash as a separate actor (e.g., `Reaper`) that
nondeterministically sends a `Kill` message to Deacon at any time, and
Deacon's WakeReady -> Crashed transition is gated on receiving Kill.
This matches the "external SIGTERM" semantic and makes the crash
boundary explicit. ~30 lines, doesn't change verification outcomes.

#### 2. The Polecat is parked via a Parker stub at t=0 -- the bake-in critique

Same shape as sling-3768's P1.3: the Polecat is in Parked because
Parker fires Park at t=0, modeling "a prior gate-blocking step put
this polecat into Parked." But the actual gate-blocking step (the
work loop encountering `bd gate wait`) isn't in the model. A
challenger could say "you've hand-waved the part where parking
happens; you only model the recovery."

Fix: extend Polecat with a Working -> Parked transition guarded on
some pre-condition (e.g., observed Gate=Open AND received an explicit
Park-trigger from a real `gt park` analog). Add a `GtPark` component
that sends Park when Polecat tries to advance and finds the gate open.
Now the trace shows the parking *as a consequence* of the gate state
plus a work step, not as a baked-in initial condition. Estimate
~60 minutes including a regression test.

#### 3. PrimeRecovery's self-heal trigger is in-memory observation, not disk

The proposed real-world fix in #3587 reads the persisted
`parked-<agent>.json` file on agent startup and queries `bd gate show
<gate-id> --json`. Our PrimeRecovery just observes Polecat and Gate
state directly. A reviewer might say "you've assumed the persistence
layer works; the actual bug surface might include 'parked.json doesn't
exist' or 'bd gate show returns stale data.'"

Fix: model the persistence as a separate `ParkedFile` actor (states:
NotPersisted, Persisted, Read) and make PrimeRecovery's transition
read from ParkedFile instead of observing Polecat directly.
Demonstrates the proposed fix actually depends on the file-write being
reliable. May surface a secondary bug where ParkedFile.Persisted lags
the Polecat=Parked transition (i.e., parked-state isn't written
synchronously enough). 1-2 hours.

### P2 — rigor

#### 4. Single Deacon, single Polecat, single Gate

Real gastown has multiple agents, each with their own gates. The bug
report's reproducer shows three accumulated parked polecats. Our model
has one of each. A challenger could say "the bug might compose
non-trivially when multiple gates resolve out of order, or when one
Deacon's crash interacts with another Deacon's gate-check."

Fix: scale to two Polecats parking on two different Gates with one
Deacon checking both. Verify HookedSingleton-equivalent (no two
parked polecats on same agent + same gate) AND PolecatEventuallyWorking
across both polecats. ~2 hours, state space probably grows to ~200
distinct states.

#### 5. No model of the `bd gate check` "only queries status=open" filter

The bug body explicitly cites this as the root cause of why a successor
Deacon can't recover: "bd gate check only queries status=open gates.
Once a gate is closed, it becomes invisible to new Deacon sessions."
Our model doesn't have multiple Deacon sessions, so this filter is
implicit -- we just have one Deacon that crashes mid-protocol.

A reviewer could say "your model demonstrates that ONE Deacon dying
breaks the protocol, but doesn't demonstrate WHY a successor Deacon
can't pick it up. The filter behavior is the load-bearing detail."

Fix: add a SuccessorDeacon component that runs after the first Deacon
has terminated (crashed or completed). Its `bd gate check` is gated
on observing Gate=Open -- if Gate=Closed, it sees nothing and exits.
Demonstrates explicitly that the closed gate is invisible to the
successor. ~1 hour.

#### 6. Liveness only -- no safety property

Sling-3768 had both safety (HookedSingleton) and liveness. Gate-3587
relies entirely on liveness for the bug demonstration. Some reviewers
prefer safety because it's compositional with proofs and doesn't
depend on fairness assumptions.

Fix: craft a safety invariant for "system is in the bug-stuck state":
no reachable state has (Polecat=Parked AND Gate=Closed AND
Deacon=Crashed AND Wake-channel=NotSent AND PrimeRecovery=Pending).
The bug spec violates this invariant whenever it reaches the stuck
state; the fix spec doesn't because PrimeRecovery transitions to Sent
quickly. Adds a safety dimension to the verification without changing
the model's structure. ~30 minutes.

### P3 — disclosure

#### 7. Multi-shot prime not modeled

Real `gt prime` fires every time an agent starts. The model's
PrimeRecovery is single-shot. If a polecat re-parks after waking, the
fix's self-heal wouldn't fire again in our model -- but a real `gt
prime` would. The model is conservative (worst-case for the fix).

Fix: comment in the spec description noting that real prime is multi-
shot and the single-shot model is a conservative under-approximation
of the fix's effective coverage. No code change.

#### 8. Issue is decorative

We bind Issue to satisfy Polecat's ISSUE_OBSERVE port, but Issue stays
at Open throughout. A reviewer reading the trace might wonder why
Issue is there and whether its decorative state-set affects anything.

Fix: header comment in the project spec explaining "Issue is bound to
satisfy Polecat.ISSUE_OBSERVE; in this scenario the work-coordination
lifecycle isn't exercised, so Issue stays Open. The convoy-lands
spec uses the same Polecat with the full lifecycle."

#### 9. Crash window is positioned at one specific point

Deacon's crash transition is only on WakeReady -> Crashed. In reality
crashes can happen anywhere (Idle, ClosingGate, even mid-Wake-send).
A challenger could say "your model only checks one crash position;
the bug might also exist if Deacon dies during Idle (no protocol
progress) or ClosingGate (Close in-flight but not delivered)."

Fix: add crash transitions from Idle, ClosingGate, and SendingWake.
TLC will explore each. Verify which interleavings result in the bug
shape (only WakeReady -> Crashed produces the stuck-Parked outcome
because it's the only point where Gate has been closed AND Wake hasn't
been sent). Strengthens the model and also demonstrates that the bug
is uniquely caused by the WakeReady -> Crashed window. ~30 minutes.

## Defense plan, ordered

1. **P1 work (90-120 min)**: external Reaper for crash, Working->Parked
   via real gate observation, ParkedFile persistence layer.
2. **P2 work (3-4 hrs)**: scale to multiple polecats + gates,
   SuccessorDeacon to demonstrate the closed-gate filter, safety
   invariant alongside liveness.
3. **P3 work (15 min)**: disclosure comments in the project header.

Total to be defensible against gastown-insider scrutiny: ~5-6 hours.

## Interim posture (do this even before P1)

Before any of the above, append a "Limitations" section to each project
spec's `description` field listing every gap above. This converts
unknown-unknowns into disclosed-knowns. A challenger who points at
the Reaper-shaped crash artifact gets: "yes, see Limitations item 1
-- known shortcut." Defensible even with the current model.

## Files

- `gate-3587-bug.kinner.json` -- the bug spec (liveness violates)
- `gate-3587-fix.kinner.json` -- the fix spec (liveness holds)
- `lib/{gate,deacon,parker,primerecovery}.kinner.json` -- new
  components for this model
- `lib/polecat.kinner.json` v0.3 -- extended with Parked + WAKE_IN
- `lib/{hook,hookcycler}.kinner.json` -- the Hook split that
  incidentally restored convoy-lands

## What done looks like

A re-runnable TLC + Python pipeline that:

1. Runs the bug spec, demonstrates liveness failure with a clear
   counterexample showing Deacon WakeReady -> Crashed.
2. Runs the fix spec, demonstrates liveness pass plus the safety
   invariant from #6.
3. Runs the multi-Polecat scaled spec from #4, shows the bug doesn't
   compound non-trivially across multiple gates / agents.
4. Runs the SuccessorDeacon spec from #5, shows the closed-gate
   filter is the real root cause of why successor sessions can't help.

The fix model with full P1+P2 coverage is the natural "case study #2
after sling-3768" -- where we *demonstrate* the proposed gt prime
change with the same rigor as the proposed sling.go change.
