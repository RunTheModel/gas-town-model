---- MODULE MR ----
(*
@kinner {
  "component": "MR",
  "version": "0.3.0",
  "description": "Merge request phase lifecycle. Absent until polecat completes. Ready = in merge queue. Processing = refinery claimed it. Merged = refinery completed the merge.",
  "ports": {
    "POLECAT_OBSERVE": {
      "direction": "observe",
      "variable": "polecatState",
      "states": [
        "Done"
      ],
      "description": "observes polecat state. Absent -> Ready when polecat = Done."
    },
    "REFINERY_IN": {
      "direction": "in",
      "variable": "refinery_inChannel",
      "description": "receives Processing and Merged events from the Refinery. Tagged 'Processing' and 'Merged'."
    }
  },
  "variables": {
    "state": "mRState",
    "refinery_inChannel": "refinery_inChannel",
    "POLECAT_OBSERVE": "polecatState"
  },
  "stateConstants": [
    "Absent",
    "Ready",
    "Processing",
    "Merged"
  ],
  "tagConstants": [
    "Merged",
    "Processing"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Absent,
    Ready,
    Processing,
    Merged,
    POLECAT_OBSERVE_Done,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    Merged,
    Processing

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    mRState,
    polecatState,
    refinery_inChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ mRState \in {Absent, Ready, Processing, Merged}
    /\ refinery_inChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Merged, Processing}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ mRState = Absent

\* -- ACTIONS ------------------------------------------------------------------
\* (Absent, polecat done: MR enters merge queue, Ready)
MR_PolecatDoneMREntersMergeQueue ==
    /\ mRState = Absent
    /\ polecatState = POLECAT_OBSERVE_Done
    /\ mRState' = Ready
    /\ UNCHANGED <<polecatState, refinery_inChannel>>

\* (Ready, refinery claims this MR for processing, Processing)
MR_RefineryClaimsThisMRForProcessing ==
    /\ mRState = Ready
    /\ refinery_inChannel = Processing
    /\ mRState' = Processing
    /\ refinery_inChannel' = Ch_Delivered
    /\ UNCHANGED <<polecatState>>

\* (Processing, refinery merged this MR, Merged)
MR_RefineryMergedThisMR ==
    /\ mRState = Processing
    /\ refinery_inChannel = Merged
    /\ mRState' = Merged
    /\ refinery_inChannel' = Ch_Delivered
    /\ UNCHANGED <<polecatState>>

\* (Merged, terminal, Merged)
MR_Terminal ==
    /\ mRState = Merged
    /\ mRState' = Merged
    /\ UNCHANGED <<polecatState, refinery_inChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       MR_PolecatDoneMREntersMergeQueue
    \/ MR_RefineryClaimsThisMRForProcessing
    \/ MR_RefineryMergedThisMR
    \/ MR_Terminal

====
