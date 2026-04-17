---- MODULE Feeder ----
(*
@kinner {
  "component": "Feeder",
  "version": "0.1.0",
  "description": "Parallel feeder. Non-deterministic dispatch order per the parallel-feeder fix from the gastown-guide monolith.",
  "ports": {
    "SLING1": {
      "direction": "out",
      "variable": "sling1Channel",
      "description": "sends Sling to the first issue. Tagged 'Sling'."
    },
    "SLING2": {
      "direction": "out",
      "variable": "sling2Channel",
      "description": "sends Sling to the second issue. Tagged 'Sling'."
    },
    "CONVOY_OBSERVE": {
      "direction": "observe",
      "variable": "convoyState",
      "states": [
        "Open"
      ],
      "description": "observes convoy state. Dispatching starts when convoy = Open."
    }
  },
  "variables": {
    "state": "feederState",
    "sling1Channel": "sling1Channel",
    "sling2Channel": "sling2Channel",
    "CONVOY_OBSERVE": "convoyState"
  },
  "stateConstants": [
    "Idle",
    "Slung1Only",
    "Slung2Only",
    "BothSlung"
  ],
  "tagConstants": [
    "Sling"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Idle,
    Slung1Only,
    Slung2Only,
    BothSlung,
    CONVOY_OBSERVE_Open,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    Sling

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    feederState,
    convoyState,
    sling1Channel,
    sling2Channel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ feederState \in {Idle, Slung1Only, Slung2Only, BothSlung}
    /\ sling1Channel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Sling}
    /\ sling2Channel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Sling}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ feederState = Idle

\* -- ACTIONS ------------------------------------------------------------------
\* (Idle, dispatch issue1 first, Slung1Only)
Feeder_DispatchIssue1First ==
    /\ feederState = Idle
    /\ convoyState = CONVOY_OBSERVE_Open
    /\ feederState' = Slung1Only
    /\ sling1Channel \in {Ch_NotSent, Ch_Delivered}
    /\ sling1Channel' = Sling
    /\ UNCHANGED <<convoyState, sling2Channel>>

\* (Idle, dispatch issue2 first, Slung2Only)
Feeder_DispatchIssue2First ==
    /\ feederState = Idle
    /\ convoyState = CONVOY_OBSERVE_Open
    /\ feederState' = Slung2Only
    /\ sling2Channel \in {Ch_NotSent, Ch_Delivered}
    /\ sling2Channel' = Sling
    /\ UNCHANGED <<convoyState, sling1Channel>>

\* (Slung1Only, dispatch issue2 too, BothSlung)
Feeder_DispatchIssue2Too ==
    /\ feederState = Slung1Only
    /\ feederState' = BothSlung
    /\ sling2Channel \in {Ch_NotSent, Ch_Delivered}
    /\ sling2Channel' = Sling
    /\ UNCHANGED <<convoyState, sling1Channel>>

\* (Slung2Only, dispatch issue1 too, BothSlung)
Feeder_DispatchIssue1Too ==
    /\ feederState = Slung2Only
    /\ feederState' = BothSlung
    /\ sling1Channel \in {Ch_NotSent, Ch_Delivered}
    /\ sling1Channel' = Sling
    /\ UNCHANGED <<convoyState, sling2Channel>>

\* (BothSlung, terminal, BothSlung)
Feeder_Terminal ==
    /\ feederState = BothSlung
    /\ feederState' = BothSlung
    /\ UNCHANGED <<convoyState, sling1Channel, sling2Channel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Feeder_DispatchIssue1First
    \/ Feeder_DispatchIssue2First
    \/ Feeder_DispatchIssue2Too
    \/ Feeder_DispatchIssue1Too
    \/ Feeder_Terminal

====
