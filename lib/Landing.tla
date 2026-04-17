---- MODULE Landing ----
(*
@kinner {
  "component": "Landing",
  "version": "0.1.0",
  "description": "Cleanup ceremony. Idle until convoy reaches Closed or ForceLandPending. Fires CLEAN to each worktree sequentially, waits for each to report Cleaned via observe, then Done.",
  "ports": {
    "CLEAN1": {
      "direction": "out",
      "variable": "clean1Channel",
      "description": "sends Clean to the first worktree. Tagged 'Clean'."
    },
    "CLEAN2": {
      "direction": "out",
      "variable": "clean2Channel",
      "description": "sends Clean to the second worktree. Tagged 'Clean'."
    },
    "CONVOY_OBSERVE": {
      "direction": "observe",
      "variable": "convoyState",
      "states": [
        "Closed",
        "ForceLandPending"
      ],
      "description": "observes convoy state to know when to start cleanup. Fires on Closed (normal) or ForceLandPending (force path)."
    },
    "WT1_OBSERVE": {
      "direction": "observe",
      "variable": "wt1State",
      "states": [
        "Cleaned"
      ],
      "description": "observes first worktree's completion."
    },
    "WT2_OBSERVE": {
      "direction": "observe",
      "variable": "wt2State",
      "states": [
        "Cleaned"
      ],
      "description": "observes second worktree's completion."
    }
  },
  "variables": {
    "state": "landingState",
    "clean1Channel": "clean1Channel",
    "clean2Channel": "clean2Channel",
    "CONVOY_OBSERVE": "convoyState",
    "WT1_OBSERVE": "wt1State",
    "WT2_OBSERVE": "wt2State"
  },
  "stateConstants": [
    "Idle",
    "Cleaning1",
    "WaitingForCleanup2",
    "Cleaning2",
    "VerifyingCleanup",
    "Done"
  ],
  "tagConstants": [
    "Clean"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Idle,
    Cleaning1,
    WaitingForCleanup2,
    Cleaning2,
    VerifyingCleanup,
    Done,
    CONVOY_OBSERVE_Closed,
    CONVOY_OBSERVE_ForceLandPending,
    WT1_OBSERVE_Cleaned,
    WT2_OBSERVE_Cleaned,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    Clean

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    landingState,
    convoyState,
    wt1State,
    wt2State,
    clean1Channel,
    clean2Channel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ landingState \in {Idle, Cleaning1, WaitingForCleanup2, Cleaning2, VerifyingCleanup, Done}
    /\ clean1Channel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Clean}
    /\ clean2Channel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Clean}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ landingState = Idle

\* -- ACTIONS ------------------------------------------------------------------
\* (Idle, convoy ready for cleanup: start wt1, Cleaning1)
Landing_ConvoyReadyForCleanupStartWt1 ==
    /\ landingState = Idle
    /\ convoyState = CONVOY_OBSERVE_Closed \/ convoyState = CONVOY_OBSERVE_ForceLandPending
    /\ landingState' = Cleaning1
    /\ clean1Channel \in {Ch_NotSent, Ch_Delivered}
    /\ clean1Channel' = Clean
    /\ UNCHANGED <<convoyState, wt1State, wt2State, clean2Channel>>

\* (Cleaning1, wt1 cleaned: prep for wt2, WaitingForCleanup2)
Landing_Wt1CleanedPrepForWt2 ==
    /\ landingState = Cleaning1
    /\ wt1State = WT1_OBSERVE_Cleaned
    /\ landingState' = WaitingForCleanup2
    /\ UNCHANGED <<convoyState, wt1State, wt2State, clean1Channel, clean2Channel>>

\* (WaitingForCleanup2, fire wt2 clean, Cleaning2)
Landing_FireWt2Clean ==
    /\ landingState = WaitingForCleanup2
    /\ landingState' = Cleaning2
    /\ clean2Channel \in {Ch_NotSent, Ch_Delivered}
    /\ clean2Channel' = Clean
    /\ UNCHANGED <<convoyState, wt1State, wt2State, clean1Channel>>

\* (Cleaning2, wt2 cleaned: verify both, VerifyingCleanup)
Landing_Wt2CleanedVerifyBoth ==
    /\ landingState = Cleaning2
    /\ wt2State = WT2_OBSERVE_Cleaned
    /\ landingState' = VerifyingCleanup
    /\ UNCHANGED <<convoyState, wt1State, wt2State, clean1Channel, clean2Channel>>

\* (VerifyingCleanup, both worktrees confirmed cleaned, Done)
Landing_BothWorktreesConfirmedCleaned ==
    /\ landingState = VerifyingCleanup
    /\ wt1State = WT1_OBSERVE_Cleaned /\ wt2State = WT2_OBSERVE_Cleaned
    /\ landingState' = Done
    /\ UNCHANGED <<convoyState, wt1State, wt2State, clean1Channel, clean2Channel>>

\* (Done, terminal, Done)
Landing_Terminal ==
    /\ landingState = Done
    /\ landingState' = Done
    /\ UNCHANGED <<convoyState, wt1State, wt2State, clean1Channel, clean2Channel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Landing_ConvoyReadyForCleanupStartWt1
    \/ Landing_Wt1CleanedPrepForWt2
    \/ Landing_FireWt2Clean
    \/ Landing_Wt2CleanedVerifyBoth
    \/ Landing_BothWorktreesConfirmedCleaned
    \/ Landing_Terminal

====
