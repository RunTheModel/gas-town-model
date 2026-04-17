---- MODULE Issue ----
(*
@kinner {
  "component": "Issue",
  "version": "0.1.0",
  "description": "The bead's work-item status. Lifecycle verified against beads/status.go:65-77 and the convoy-lands monolith. Open -> Hooked is the slung-by-feeder write. Hooked -> InProgress is the polecat-prime write (real gastown: polecat_spawn.go:404 SetState(StateWorking) AFTER SetAgentState('working') -- the asymmetric write order from beads-lifecycle.kinner.json). InProgress -> Closed is the bd.Close(hookedBeadID) call from done.go:1588. Other states (Blocked, Tombstone) deferred -- this component models the happy-path lifecycle.",
  "ports": {
    "SLING": {
      "direction": "in",
      "variable": "slingChannel",
      "description": "receives a sling assignment from Feeder. Advances Open -> Hooked. Tagged 'Sling' to match the Feeder's send."
    },
    "POLECAT_OBSERVE": {
      "direction": "observe",
      "variable": "polecatState",
      "states": [
        "Working",
        "Done"
      ],
      "description": "observes the assigned polecat's state. Hooked -> InProgress fires when polecat = Working; InProgress -> Closed fires when polecat = Done."
    }
  },
  "variables": {
    "state": "issueState",
    "slingChannel": "slingChannel",
    "POLECAT_OBSERVE": "polecatState"
  },
  "stateConstants": [
    "Open",
    "Hooked",
    "InProgress",
    "Closed"
  ],
  "tagConstants": [
    "Sling"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Open,
    Hooked,
    InProgress,
    Closed,
    POLECAT_OBSERVE_Working,
    POLECAT_OBSERVE_Done,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    Sling

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    issueState,
    polecatState,
    slingChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ issueState \in {Open, Hooked, InProgress, Closed}
    /\ slingChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Sling}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ issueState = Open

\* -- ACTIONS ------------------------------------------------------------------
\* (Open, feeder slings: issue gets hooked to a polecat (sling.go:918 hookBeadWithRetry), Hooked)
Issue_FeederSlingsIssueGetsHookedToAPolecatSlingGo918HookBeadWithRetry ==
    /\ issueState = Open
    /\ slingChannel = Sling
    /\ issueState' = Hooked
    /\ slingChannel' = Ch_Delivered
    /\ UNCHANGED <<polecatState>>

\* (Hooked, polecat starts working: issue advances to in-progress (polecat_spawn.go:404 SetState(StateWorking)), InProgress)
Issue_PolecatStartsWorkingIssueAdvancesToInProgressPolecatSpawnGo404SetStateStateWorking ==
    /\ issueState = Hooked
    /\ polecatState = POLECAT_OBSERVE_Working
    /\ issueState' = InProgress
    /\ UNCHANGED <<polecatState, slingChannel>>

\* (InProgress, polecat finishes (gt done): issue closes (done.go:1588 bd.Close(hookedBeadID)), Closed)
Issue_PolecatFinishesGtDoneIssueClosesDoneGo1588BdCloseHookedBeadID ==
    /\ issueState = InProgress
    /\ polecatState = POLECAT_OBSERVE_Done
    /\ issueState' = Closed
    /\ UNCHANGED <<polecatState, slingChannel>>

\* (Closed, terminal, Closed)
Issue_Terminal ==
    /\ issueState = Closed
    /\ issueState' = Closed
    /\ UNCHANGED <<polecatState, slingChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Issue_FeederSlingsIssueGetsHookedToAPolecatSlingGo918HookBeadWithRetry
    \/ Issue_PolecatStartsWorkingIssueAdvancesToInProgressPolecatSpawnGo404SetStateStateWorking
    \/ Issue_PolecatFinishesGtDoneIssueClosesDoneGo1588BdCloseHookedBeadID
    \/ Issue_Terminal

====
