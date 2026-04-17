# convoy-lands -- composed application sketch

**Status**: design sketch. The application spec doesn't exist yet
because three of its four required library components don't exist
yet (only Polecat is built). This document is the shape we're
aiming for; we build the components to fit it.

## What it is

The composed re-implementation of `earhart-wip/gastown-guide/
convoy-lands.kinner.json` (the 14-actor monolith we built and
hardened earlier). Same end-to-end coverage of Mayor → Convoy →
Feeder → Polecats → Issues → MRs → Refinery → Landing →
Worktree-cleanup. Same cross-cutting safety invariants. But built
out of reusable library components, so adding a third issue
(or N-th issue) is an extra `components` entry, not 3 more
hand-written actors.

## Architecture

**Singletons at top level** (project-level inline actors):

| Actor | Role |
|---|---|
| `Mayor` | initiates convoy; chooses Land or ForceLand |
| `Convoy` | the convoy bead; tracks AllDone → Closed → Landed |
| `Feeder` | dispatches Slings to per-issue Polecats |
| `Refinery` | shared queue receiving MergeReady from all Polecats |
| `Landing` | the cleanup ceremony; orchestrates worktree removal |

**Per-issue components** (2 issues for the first cut, N later):

| Component | What it models | Status |
|---|---|---|
| `Polecat` | Absent → Working → Done → Idle + HOOK_IN orthogonal | **EXISTS** at `lib/polecat.kinner.json` |
| `Issue` | Open → Hooked → InProgress → Closed | TBD |
| `MR` | Absent → Ready → Processing → Merged + FailureType | TBD |
| `Worktree` | Present → Cleaned | TBD |

For 2 issues: 8 component instances total (Pol1/Pol2, Iss1/Iss2,
Mr1/Mr2, Wt1/Wt2). For N issues: 4N instances.

## Component port surfaces (proposed)

### Polecat (already built)

```
in:       SLING (from Feeder)
out:      MERGE_READY (to Refinery)
in:       HOOK_IN (substrate; convoy-lands leaves unbound or stubbed)
observe:  ISSUE_OBSERVE (the polecat's assigned Issue)
```

### Issue (TBD)

```
in:       SLING (from Feeder; same channel as Polecat receives sling? or separate?)
observe:  POLECAT_OBSERVE (advances Hooked→InProgress when Polecat=Working;
                           advances InProgress→Closed when Polecat=Done)
```

### MR (TBD)

```
in:       MERGE_READY (from Polecat; alternatively just observed)
out:      MERGED_NOTIFY (to Polecat; alternatively just observed by Polecat)
observe:  POLECAT_OBSERVE (Absent→Ready when Polecat=Done)
observe:  REFINERY_OBSERVE (Ready→Processing→Merged driven by Refinery state)
```

The MR shape is the most uncertain. Two viable designs:
- **Channel-driven**: MR receives MergeReady from Polecat, sends
  Merged back. More edges in the interaction graph.
- **Observe-driven**: MR observes Polecat and Refinery, advances
  state via guards. Fewer channels (cheaper for TLC per the
  "channels multiply, observes scale" chapter).

I'd start with observe-driven and switch to channels if we find a
case that needs them.

### Worktree (TBD)

```
in:       CLEAN (from Landing)
```

Trivial. State Present → Cleaned on receive.

## Bindings (sketch)

```json
{
  "name": "ConvoyLands",
  "messageSet": ["Sling", "MergeReady", "Land", "ForceLand", "ConvoyDone", "Clean"],

  "actors": [
    {"name": "Mayor", ...},
    {"name": "Convoy", ...},
    {"name": "Feeder", ...},
    {"name": "Refinery", ...},
    {"name": "Landing", ...}
  ],

  "components": [
    {"use": "Polecat",  "as": "Pol1", "bind": {"SLING": "Feeder", "MERGE_READY": "Refinery", "HOOK_IN": "<stub>", "ISSUE_OBSERVE": "Iss1"}},
    {"use": "Polecat",  "as": "Pol2", "bind": {"SLING": "Feeder", "MERGE_READY": "Refinery", "HOOK_IN": "<stub>", "ISSUE_OBSERVE": "Iss2"}},
    {"use": "Issue",    "as": "Iss1", "bind": {"SLING": "Feeder", "POLECAT_OBSERVE": "Pol1"}},
    {"use": "Issue",    "as": "Iss2", "bind": {"SLING": "Feeder", "POLECAT_OBSERVE": "Pol2"}},
    {"use": "MR",       "as": "Mr1",  "bind": {"POLECAT_OBSERVE": "Pol1", "REFINERY_OBSERVE": "Refinery"}},
    {"use": "MR",       "as": "Mr2",  "bind": {"POLECAT_OBSERVE": "Pol2", "REFINERY_OBSERVE": "Refinery"}},
    {"use": "Worktree", "as": "Wt1",  "bind": {"CLEAN": "Landing"}},
    {"use": "Worktree", "as": "Wt2",  "bind": {"CLEAN": "Landing"}}
  ],
  ...
}
```

Open question: HOOK_IN. The Polecat component has it, convoy-lands
doesn't model substrate hooks. Three options:
- **Stub**: bind to a project-level dummy actor that never fires
- **Drop from Polecat for convoy-lands purposes**: contradicts the
  "ONE polecat" rule
- **Make HOOK_IN an optional port**: requires compiler change

Stub for now. If many applications skip HOOK_IN, "optional ports"
becomes a real backlog item.

## Cross-cutting invariants (using 062 dotted syntax)

The whole point of decomposing was to make these invariants
expressible across instance state. These are the load-bearing
properties; they're what convoy-lands existed to verify.

```
NormalLandMeansWorkIntegrated:
  convoy # Convoy.Landed
  \/ (Iss1.issue = Iss1.Closed /\ Iss2.issue = Iss2.Closed
      /\ Mr1.mr = Mr1.Merged   /\ Mr2.mr = Mr2.Merged)

PolecatsIdleAtLanding:
  convoy # Convoy.Landed
  \/ (Pol1.polecat = Pol1.Idle /\ Pol2.polecat = Pol2.Idle)

WorktreeCleanupHappensOnLand:
  convoy \notin {Convoy.Landed, Convoy.LandedForce}
  \/ (Wt1.worktree = Wt1.Cleaned /\ Wt2.worktree = Wt2.Cleaned)

ForceLandIsExplicit:
  convoy # Convoy.LandedForce \/ mayor = Mayor.ForceLanding
```

**062 + 063 pay off here.** Without 062 these invariants couldn't
be expressed in source-level Kinner (`Iss1.issue = Iss1.Closed`
wouldn't resolve). Without 063 the typed sends between Polecats
and Refinery (`MergeReady` tag distinguishing which Polecat sent
the signal) would silently drop. Both unblock this spec.

## State-space estimate

The monolith reaches **680,556 distinct safety states** for 2
issues. The decomposed version should reach a similar count --
the abstraction doesn't change reachable states, only how they're
described in the spec.

Risk: composition overhead. If TLC re-evaluates each module's
INSTANCE per state instead of flattening, the cost could spike.
Open question per memory `project_tlc_instance_perf.md`. We'll
measure and report.

## Build order

1. **Issue** component (smallest after Polecat; ~5 states, 2 ports)
2. **Worktree** component (trivial; 2 states, 1 port)
3. **MR** component (most uncertain shape; 4-5 states + FailureType)
4. **convoy-lands.kinner.json** application sketch made real
5. Verify TLC accepts and produces matching state count to the monolith
6. Add 3rd issue, then 4th -- prove the N-issue scaling claim
7. Cross-cutting invariants -- verify they hold (or surface a real bug)

## What this sketch does NOT settle

- **MR's design** (channel-driven vs observe-driven). Pick when we
  build it.
- **HOOK_IN handling for convoy-lands**. Stub for now; revisit if
  many applications skip it.
- **Whether Issue receives Sling from Feeder or observes a Polecat
  state change to advance**. Probably both: Sling carries the
  hook event from outside, Polecat state drives subsequent Issue
  transitions.
- **Whether the convoy-lands monolith itself becomes obsolete or
  stays as a comparison point**. Keep it; the comparison is
  load-bearing for the chapter.

## Comparison to current model

| Property | `gastown-guide/convoy-lands.kinner.json` (monolith) | `kinner-gastown/convoy-lands.kinner.json` (decomposed, planned) |
|---|---|---|
| Actors at top level | 14 | 5 |
| Component instances | 0 | 8 (4 per issue × 2 issues) |
| Library components used | 0 | 4 (Polecat, Issue, MR, Worktree) |
| Cross-cutting invariants | 3 (using underscored TLA names) | 4 (using dotted syntax from 062) |
| Adding a third issue | hand-write 4 more actors | one entry per component (4 lines) |
| Substrate-layer modeling | none | HOOK_IN port on Polecat (unbound here, exercised elsewhere) |
| State count (safety) | 680,556 distinct | TBD; expected similar |
