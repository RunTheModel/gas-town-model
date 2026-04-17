---- MODULE Refinery ----
(*
@kinner {
  "component": "Refinery",
  "version": "0.2.0",
  "description": "Shared merge queue. Sequential processing. Receives MergeReady, notifies the relevant MR, processes, notifies merged, returns to idle.",
  "ports": {
    "MERGE_READY1": {
      "direction": "in",
      "variable": "merge_ready1Channel",
      "description": "receives MergeReady from polecat 1. Tagged 'MergeReady'."
    },
    "MERGE_READY2": {
      "direction": "in",
      "variable": "merge_ready2Channel",
      "description": "receives MergeReady from polecat 2. Tagged 'MergeReady'."
    },
    "MR_NOTIFY1": {
      "direction": "out",
      "variable": "mr_notify1Channel",
      "description": "notifies MR 1 of processing and merge completion. Tagged 'Processing' or 'Merged'."
    },
    "MR_NOTIFY2": {
      "direction": "out",
      "variable": "mr_notify2Channel",
      "description": "notifies MR 2 of processing and merge completion. Tagged 'Processing' or 'Merged'."
    }
  },
  "variables": {
    "state": "refineryState",
    "merge_ready1Channel": "merge_ready1Channel",
    "merge_ready2Channel": "merge_ready2Channel",
    "mr_notify1Channel": "mr_notify1Channel",
    "mr_notify2Channel": "mr_notify2Channel"
  },
  "stateConstants": [
    "Idle",
    "ProcessingMR1",
    "ProcessingMR2"
  ],
  "tagConstants": [
    "MergeReady",
    "Merged",
    "Processing"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Idle,
    ProcessingMR1,
    ProcessingMR2,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    MergeReady,
    Merged,
    Processing

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    refineryState,
    merge_ready1Channel,
    merge_ready2Channel,
    mr_notify1Channel,
    mr_notify2Channel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ refineryState \in {Idle, ProcessingMR1, ProcessingMR2}
    /\ merge_ready1Channel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {MergeReady, Merged, Processing}
    /\ merge_ready2Channel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {MergeReady, Merged, Processing}
    /\ mr_notify1Channel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {MergeReady, Merged, Processing}
    /\ mr_notify2Channel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {MergeReady, Merged, Processing}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ refineryState = Idle

\* -- ACTIONS ------------------------------------------------------------------
\* (Idle, receives MergeReady from polecat1: claim MR1, ProcessingMR1)
Refinery_ReceivesMergeReadyFromPolecat1ClaimMR1 ==
    /\ refineryState = Idle
    /\ merge_ready1Channel = MergeReady
    /\ refineryState' = ProcessingMR1
    /\ merge_ready1Channel' = Ch_Delivered
    /\ UNCHANGED <<merge_ready2Channel, mr_notify1Channel, mr_notify2Channel>>

\* (ProcessingMR1, notify MR1 it is being processed, ProcessingMR1)
Refinery_NotifyMR1ItIsBeingProcessed ==
    /\ refineryState = ProcessingMR1
    /\ refineryState' = ProcessingMR1
    /\ mr_notify1Channel \in {Ch_NotSent, Ch_Delivered}
    /\ mr_notify1Channel' = Processing
    /\ UNCHANGED <<merge_ready1Channel, merge_ready2Channel, mr_notify2Channel>>

\* (ProcessingMR1, MR1 merged: notify and return to idle, Idle)
Refinery_MR1MergedNotifyAndReturnToIdle ==
    /\ refineryState = ProcessingMR1
    /\ refineryState' = Idle
    /\ mr_notify1Channel \in {Ch_NotSent, Ch_Delivered}
    /\ mr_notify1Channel' = Merged
    /\ UNCHANGED <<merge_ready1Channel, merge_ready2Channel, mr_notify2Channel>>

\* (Idle, receives MergeReady from polecat2: claim MR2, ProcessingMR2)
Refinery_ReceivesMergeReadyFromPolecat2ClaimMR2 ==
    /\ refineryState = Idle
    /\ merge_ready2Channel = MergeReady
    /\ refineryState' = ProcessingMR2
    /\ merge_ready2Channel' = Ch_Delivered
    /\ UNCHANGED <<merge_ready1Channel, mr_notify1Channel, mr_notify2Channel>>

\* (ProcessingMR2, notify MR2 it is being processed, ProcessingMR2)
Refinery_NotifyMR2ItIsBeingProcessed ==
    /\ refineryState = ProcessingMR2
    /\ refineryState' = ProcessingMR2
    /\ mr_notify2Channel \in {Ch_NotSent, Ch_Delivered}
    /\ mr_notify2Channel' = Processing
    /\ UNCHANGED <<merge_ready1Channel, merge_ready2Channel, mr_notify1Channel>>

\* (ProcessingMR2, MR2 merged: notify and return to idle, Idle)
Refinery_MR2MergedNotifyAndReturnToIdle ==
    /\ refineryState = ProcessingMR2
    /\ refineryState' = Idle
    /\ mr_notify2Channel \in {Ch_NotSent, Ch_Delivered}
    /\ mr_notify2Channel' = Merged
    /\ UNCHANGED <<merge_ready1Channel, merge_ready2Channel, mr_notify1Channel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Refinery_ReceivesMergeReadyFromPolecat1ClaimMR1
    \/ Refinery_NotifyMR1ItIsBeingProcessed
    \/ Refinery_MR1MergedNotifyAndReturnToIdle
    \/ Refinery_ReceivesMergeReadyFromPolecat2ClaimMR2
    \/ Refinery_NotifyMR2ItIsBeingProcessed
    \/ Refinery_MR2MergedNotifyAndReturnToIdle

====
