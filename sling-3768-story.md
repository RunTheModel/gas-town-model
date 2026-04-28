# sling-3768: a story about safety, liveness, and the limits of bounded models

A modeling session in late April 2026 took gastown issue #3768 from "verify the
bug exists" to "verify the proposed fix works" to "wait, why doesn't the fix's
liveness check pass" to a structural insight about model fidelity. This is the
narrative.

## The starting point

Issue #3768 says: `gt sling <patrol-formula> <agent>` doesn't check whether
the target agent already has a hooked mol of the same formula. Restarted
agents accumulate hooked patrol mols -- the bug report shows 3+ in one
account. Sling's per-assignee lock serializes invocations but doesn't enforce
the singleton-by-formula contract.

The model lives at `sling-3768-bug.kinner.json`. It composes a substrate
(Hook + Agent + HandoffCycle + Mailbox + Pane all looping for maxCycles=3)
with three Patrol+Sling+Bead lanes contending for an AssigneeLock. The
HookedSingleton invariant is pairwise formula-keyed: no two beads of the
same formula are simultaneously Hooked.

TLC violates HookedSingleton at depth 30, ~5 seconds, 18k distinct states.
Bug demonstrated.

## Phase 1: prove the fix

Built `sling-3768-fix.kinner.json` paired with two new components:

- **BeadCloseable**: Bead variant with HOOK + CLOSE ports. Enum-state
  lifecycle (Open / Hooked / Closed) because Kinner's observe-port doesn't
  expose typed-int variables to a remote observer (filed as
  `earhart/backlog/152-typed-enum-variables.md`).
- **SlingWithCheck**: 7-state Sling that closes the same-formula sibling
  before hooking its target, then waits for target=Hooked before releasing
  the lock. Mirrors real synchronous `hookBeadWithRetry` semantics.

TLC: 60,984 distinct states, depth 80, ~6 seconds. Model checking completed.
HookedSingleton holds.

The "design -> prove -> generate" pitch made concrete: same Kinner spec, two
targets. TLC verifies; Python target generates a runnable simulator.
Random-seeded Python runs at 200 seeds: bug violates 100% (with simpler
Patrol), fix violates 0%.

This was the natural stopping point for many model authors. We kept going.

## Phase 2: liveness exposes the iceberg

The user asked: shouldn't we also be doing liveness testing? Adding properties
like `<>(Sl1=Done /\ Sl2=Done)` to verify the system *makes progress*, not
just that it doesn't break safety.

TLC ran the fix spec with the new properties and reported:

> Error: Temporal properties were violated.

A 60-step lasso where the substrate cycled, Sl1 progressed, but Sl2 never
reached Done. The fix had a liveness bug.

### Iteration 1: latch the Patrol observation

The first hypothesis: Patrol's `agent=Resumed` enable oscillates (true during
Resumed windows, false otherwise). WF on an oscillating-enabled action
doesn't force firing. With maxCycles=3, agent reaches Resumed only finitely
often -- SF doesn't help either.

Patrol v0.4: split the fire transition into a latch (`Pending -> Armed: agent=Resumed`)
plus a monotonically-enabled fire (`Armed -> Slung`).

Re-verify: still fails liveness. New counterexample showed a different
race -- Bead2 reaching Closed before Sl2 could observe Hooked.

### Iteration 2: conditional close

Drilling into the new counterexample: Sl1 sent Close to Bead2 when Bead2 was
still Open (Sl1's first run, no sibling yet Hooked). Bead2 received that
Close as a no-op consumer. Then later, Sl2 hooked Bead2 (Open -> Hooked).
But the channel state vs. the bead's actual close order can race in TLC:
the stale Close from Sl1 could be delivered AFTER Sl2's HOOK landed. Bead2
went Hooked -> Closed by an obsolete message, leaving Sl2 stuck waiting for
target=Hooked.

The fix-to-the-fix: SlingWithCheck v0.2 should only send Close if the
sibling is *actually* currently Hooked. Real `bd.Close(siblings, formula)`
operates on the existing Hooked-set; it doesn't iterate over Open beads.

Re-verify: still fails liveness. Different state, same shape -- Ptl1 never
fires, Sl1 stays in Idle.

### The structural realization

Three iterations in, the diagnosis became unavoidable: **bounded substrate
plus WF/SF cannot satisfy liveness for an actor whose enable depends on a
finitely-occurring event.**

The substrate has maxCycles=3, so agent reaches Resumed exactly 3 times.
Patrol's enable (`agent=Resumed`) is true only during those windows. WF
requires *continuous* enabling for an infinite suffix; SF requires *infinite
many* enabled states. Both fail when enabling is finite.

A behavior where Ptl1 misses every Resumed window, with Ptl2 winning all
three, is technically permitted by the fairness assumptions. TLC dutifully
finds it and reports a counterexample.

The user articulated the resolution: **safety in finite bounds, liveness in
infinite bounds = solid finding.**

### Iteration 3: drop the agent observation

Real witness/refinery patrols nominally watch agent state, but for #3768 the
timing isn't load-bearing -- the bug is about the close-step inside
sling.go, not about when Patrol decides to fire. The model captures the
bug regardless of Patrol timing relative to the substrate.

Patrol v0.5: drop `AGENT_OBSERVE` entirely. `Pending -> Slung` is
monotonically enabled (true from the initial state until the transition
fires). WF guarantees firing.

The substrate (Hook+Agent+HandoffCycle+Mailbox+Pane) still cycles for
narrative completeness but no longer gates Patrol firing.

Re-verify: TLC explores 102,465 distinct states for the fix, "Model checking
completed. No error has been found." Both safety AND liveness verified.
The bug spec still violates HookedSingleton (safety) at depth 28; with the
simpler Patrol every bug-spec random run finds the violation (200/200
seeds at 100%).

## What we learned

1. **Safety and liveness are different questions; they need different
   proofs.** Safety proves "nothing bad happens at any reachable state."
   Liveness proves "something good eventually happens on every fair
   behavior." The first works on bounded state spaces; the second needs
   infinite suffixes to reason about fairness.

2. **WF on oscillating-enabled actions is a trap.** A reasonable-looking
   model (Patrol observes agent state and fires on Resumed) compiles with
   `WF_vars(Patrol_Step)` and looks fair. But under WF semantics, an
   oscillating-enabled action is permitted to never fire. SF would help in
   the unbounded case, but Kinner currently emits only WF (component-level).
   This is worth filing as a future direction.

3. **Bounded substrate + WF fairness can't guarantee progress.** Three
   maxCycles means three Resumed visits. Even with SF, a finitely-enabled
   action isn't guaranteed by fairness. Bounded models are great for
   safety, structurally weak for liveness.

4. **Real-world patrols are scheduled by external clocks, not by observed
   agent state.** The model's agent-observation gate was narrative
   coherence, not load-bearing logic. Dropping it made the spec more
   liveness-friendly without compromising the bug demonstration.

5. **Iteration finds depth.** Each round of "verify -> find issue -> fix"
   peeled a layer. The model that verifies cleanly is more honest than the
   first version that "looked right."

## Outputs

- `sling-3768-bug.kinner.json` -- bug spec, safety only. TLC violates
  HookedSingleton; Python runs violate 100/200 seeds.
- `sling-3768-fix.kinner.json` -- fix spec, safety AND liveness. TLC: 102k
  states explored, no errors. Python: 0/200 seeds violate.
- `lib/slingwithcheck.kinner.json` -- the proposed fix to sling.go in
  spec form: between `tryAcquireSlingAssigneeLock` and `hookBeadWithRetry`,
  insert `bd.Close(siblings, formula)` IF such siblings exist.
- `lib/beadcloseable.kinner.json` -- Bead variant with CLOSE port.
- `lib/patrol.kinner.json` -- Patrol v0.5 (no agent observation; substrate
  is decorative).

## Backlog items filed in earhart from this session

- `151-no-sender-binding-sugar.md` -- explicit-null binding for "this in-port
  has no upstream sender" (surfaced when modeling the prior-bead concept
  before the multi-cycle redesign subsumed it).
- `152-typed-enum-variables.md` -- enum-typed variables observable
  cross-actor (surfaced when SlingWithCheck needed to observe a sibling's
  lifecycle status).

The natural next item, not yet filed: **per-action strong fairness in
Kinner.** Component-level WF emits today; SF would unblock liveness on
bounded models for actions whose enable is intermittent but eventual.
