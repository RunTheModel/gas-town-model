---- MODULE Convoy ----
(*
@kinner {
  "component": "Convoy",
  "version": "0.1.0",
  "description": "Convoy bead lifecycle. Staged -> Open -> AllDone -> Closed -> Landed (normal). Open -> ForceLandPending -> LandedForce (force). Both landing paths gate on Landing = Done.",
  "ports": {
    "LAUNCH": {
      "direction": "in",
      "variable": "launchChannel",
      "description": "receives Launch from Mayor. Tagged 'Launch'."
    },
    "LAND": {
      "direction": "in",
      "variable": "landChannel",
      "description": "receives Land or ForceLand from Mayor. Tagged 'Land' or 'ForceLand'."
    },
    "CONVOY_DONE": {
      "direction": "out",
      "variable": "convoy_doneChannel",
      "description": "sends ConvoyDone to Mayor when all work is complete. Tagged 'ConvoyDone'."
    },
    "ISS1_OBSERVE": {
      "direction": "observe",
      "variable": "iss1State",
      "states": [
        "Closed"
      ],
      "description": "observes issue 1 for the AllDone guard."
    },
    "ISS2_OBSERVE": {
      "direction": "observe",
      "variable": "iss2State",
      "states": [
        "Closed"
      ],
      "description": "observes issue 2 for the AllDone guard."
    },
    "MR1_OBSERVE": {
      "direction": "observe",
      "variable": "mr1State",
      "states": [
        "Merged"
      ],
      "description": "observes MR 1 for the AllDone guard."
    },
    "MR2_OBSERVE": {
      "direction": "observe",
      "variable": "mr2State",
      "states": [
        "Merged"
      ],
      "description": "observes MR 2 for the AllDone guard."
    },
    "POL1_OBSERVE": {
      "direction": "observe",
      "variable": "pol1State",
      "states": [
        "Idle"
      ],
      "description": "observes polecat 1 for the AllDone guard."
    },
    "POL2_OBSERVE": {
      "direction": "observe",
      "variable": "pol2State",
      "states": [
        "Idle"
      ],
      "description": "observes polecat 2 for the AllDone guard."
    },
    "LANDING_OBSERVE": {
      "direction": "observe",
      "variable": "landingState",
      "states": [
        "Done"
      ],
      "description": "observes Landing completion. Gates both Closed->Landed and ForceLandPending->LandedForce."
    }
  },
  "variables": {
    "state": "convoyState",
    "launchChannel": "launchChannel",
    "landChannel": "landChannel",
    "convoy_doneChannel": "convoy_doneChannel",
    "ISS1_OBSERVE": "iss1State",
    "ISS2_OBSERVE": "iss2State",
    "MR1_OBSERVE": "mr1State",
    "MR2_OBSERVE": "mr2State",
    "POL1_OBSERVE": "pol1State",
    "POL2_OBSERVE": "pol2State",
    "LANDING_OBSERVE": "landingState"
  },
  "stateConstants": [
    "Staged",
    "Open",
    "AllDone",
    "Closed",
    "ForceLandPending",
    "Landed",
    "LandedForce"
  ],
  "tagConstants": [
    "ConvoyDone",
    "ForceLand",
    "Land",
    "Launch"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Staged,
    Open,
    AllDone,
    Closed,
    ForceLandPending,
    Landed,
    LandedForce,
    ISS1_OBSERVE_Closed,
    ISS2_OBSERVE_Closed,
    MR1_OBSERVE_Merged,
    MR2_OBSERVE_Merged,
    POL1_OBSERVE_Idle,
    POL2_OBSERVE_Idle,
    LANDING_OBSERVE_Done,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    ConvoyDone,
    ForceLand,
    Land,
    Launch

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    convoyState,
    iss1State,
    iss2State,
    mr1State,
    mr2State,
    pol1State,
    pol2State,
    landingState,
    launchChannel,
    landChannel,
    convoy_doneChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ convoyState \in {Staged, Open, AllDone, Closed, ForceLandPending, Landed, LandedForce}
    /\ launchChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {ConvoyDone, ForceLand, Land, Launch}
    /\ landChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {ConvoyDone, ForceLand, Land, Launch}
    /\ convoy_doneChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {ConvoyDone, ForceLand, Land, Launch}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ convoyState = Staged

\* -- ACTIONS ------------------------------------------------------------------
\* (Staged, Launch received from Mayor, Open)
Convoy_LaunchReceivedFromMayor ==
    /\ convoyState = Staged
    /\ launchChannel = Launch
    /\ convoyState' = Open
    /\ launchChannel' = Ch_Delivered
    /\ UNCHANGED <<iss1State, iss2State, mr1State, mr2State, pol1State, pol2State, landingState, landChannel, convoy_doneChannel>>

\* (Open, all-done: all issues closed, MRs merged, polecats idle, AllDone)
Convoy_AllDoneAllIssuesClosedMRsMergedPolecatsIdle ==
    /\ convoyState = Open
    /\ iss1State = ISS1_OBSERVE_Closed /\ iss2State = ISS2_OBSERVE_Closed /\ mr1State = MR1_OBSERVE_Merged /\ mr2State = MR2_OBSERVE_Merged /\ pol1State = POL1_OBSERVE_Idle /\ pol2State = POL2_OBSERVE_Idle
    /\ convoyState' = AllDone
    /\ UNCHANGED <<iss1State, iss2State, mr1State, mr2State, pol1State, pol2State, landingState, launchChannel, landChannel, convoy_doneChannel>>

\* (AllDone, convoy reports complete to Mayor, Closed)
Convoy_ConvoyReportsCompleteToMayor ==
    /\ convoyState = AllDone
    /\ convoyState' = Closed
    /\ convoy_doneChannel \in {Ch_NotSent, Ch_Delivered}
    /\ convoy_doneChannel' = ConvoyDone
    /\ UNCHANGED <<iss1State, iss2State, mr1State, mr2State, pol1State, pol2State, landingState, launchChannel, landChannel>>

\* (Closed, Land received: convoy lands normally, Landed)
Convoy_LandReceivedConvoyLandsNormally ==
    /\ convoyState = Closed
    /\ landChannel = Land
    /\ landingState = LANDING_OBSERVE_Done
    /\ convoyState' = Landed
    /\ landChannel' = Ch_Delivered
    /\ UNCHANGED <<iss1State, iss2State, mr1State, mr2State, pol1State, pol2State, landingState, launchChannel, convoy_doneChannel>>

\* (Open, ForceLand received: convoy enters pending (cleanup first), ForceLandPending)
Convoy_ForceLandReceivedConvoyEntersPendingCleanupFirst ==
    /\ convoyState = Open
    /\ landChannel = ForceLand
    /\ convoyState' = ForceLandPending
    /\ landChannel' = Ch_Delivered
    /\ UNCHANGED <<iss1State, iss2State, mr1State, mr2State, pol1State, pol2State, landingState, launchChannel, convoy_doneChannel>>

\* (ForceLandPending, cleanup complete: convoy force-lands, LandedForce)
Convoy_CleanupCompleteConvoyForceLands ==
    /\ convoyState = ForceLandPending
    /\ landingState = LANDING_OBSERVE_Done
    /\ convoyState' = LandedForce
    /\ UNCHANGED <<iss1State, iss2State, mr1State, mr2State, pol1State, pol2State, landingState, launchChannel, landChannel, convoy_doneChannel>>

\* (Landed, terminal (normal), Landed)
Convoy_TerminalNormal ==
    /\ convoyState = Landed
    /\ convoyState' = Landed
    /\ UNCHANGED <<iss1State, iss2State, mr1State, mr2State, pol1State, pol2State, landingState, launchChannel, landChannel, convoy_doneChannel>>

\* (LandedForce, terminal (force), LandedForce)
Convoy_TerminalForce ==
    /\ convoyState = LandedForce
    /\ convoyState' = LandedForce
    /\ UNCHANGED <<iss1State, iss2State, mr1State, mr2State, pol1State, pol2State, landingState, launchChannel, landChannel, convoy_doneChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Convoy_LaunchReceivedFromMayor
    \/ Convoy_AllDoneAllIssuesClosedMRsMergedPolecatsIdle
    \/ Convoy_ConvoyReportsCompleteToMayor
    \/ Convoy_LandReceivedConvoyLandsNormally
    \/ Convoy_ForceLandReceivedConvoyEntersPendingCleanupFirst
    \/ Convoy_CleanupCompleteConvoyForceLands
    \/ Convoy_TerminalNormal
    \/ Convoy_TerminalForce

====
