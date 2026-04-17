---- MODULE Mayor ----
(*
@kinner {
  "component": "Mayor",
  "version": "0.1.0",
  "description": "Mayor agent. Running -> LaunchingConvoy -> Observing -> {NormalLanding, ForceLanding} -> Done.",
  "ports": {
    "LAUNCH": {
      "direction": "out",
      "variable": "launchChannel",
      "description": "sends Launch to the convoy bead to initiate. Tagged 'Launch'."
    },
    "LAND": {
      "direction": "out",
      "variable": "landChannel",
      "description": "sends Land or ForceLand to the convoy bead to land. Tagged 'Land' or 'ForceLand'."
    },
    "CONVOY_DONE": {
      "direction": "in",
      "variable": "convoy_doneChannel",
      "description": "receives ConvoyDone from the convoy bead when all work is complete. Tagged 'ConvoyDone'."
    }
  },
  "variables": {
    "state": "mayorState",
    "launchChannel": "launchChannel",
    "landChannel": "landChannel",
    "convoy_doneChannel": "convoy_doneChannel"
  },
  "stateConstants": [
    "Running",
    "LaunchingConvoy",
    "Observing",
    "NormalLanding",
    "ForceLanding",
    "Done"
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
    Running,
    LaunchingConvoy,
    Observing,
    NormalLanding,
    ForceLanding,
    Done,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    ConvoyDone,
    ForceLand,
    Land,
    Launch

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    mayorState,
    launchChannel,
    landChannel,
    convoy_doneChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ mayorState \in {Running, LaunchingConvoy, Observing, NormalLanding, ForceLanding, Done}
    /\ launchChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {ConvoyDone, ForceLand, Land, Launch}
    /\ landChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {ConvoyDone, ForceLand, Land, Launch}
    /\ convoy_doneChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {ConvoyDone, ForceLand, Land, Launch}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ mayorState = Running

\* -- ACTIONS ------------------------------------------------------------------
\* (Running, mayor launches the convoy, LaunchingConvoy)
Mayor_MayorLaunchesTheConvoy ==
    /\ mayorState = Running
    /\ mayorState' = LaunchingConvoy
    /\ launchChannel \in {Ch_NotSent, Ch_Delivered}
    /\ launchChannel' = Launch
    /\ UNCHANGED <<landChannel, convoy_doneChannel>>

\* (LaunchingConvoy, launch sent, mayor observes, Observing)
Mayor_LaunchSentMayorObserves ==
    /\ mayorState = LaunchingConvoy
    /\ mayorState' = Observing
    /\ UNCHANGED <<launchChannel, landChannel, convoy_doneChannel>>

\* (Observing, convoy reports complete: mayor prepares normal land, NormalLanding)
Mayor_ConvoyReportsCompleteMayorPreparesNormalLand ==
    /\ mayorState = Observing
    /\ convoy_doneChannel = ConvoyDone
    /\ mayorState' = NormalLanding
    /\ convoy_doneChannel' = Ch_Delivered
    /\ UNCHANGED <<launchChannel, landChannel>>

\* (Observing, operator chooses force-land (gt convoy land --force), ForceLanding)
Mayor_OperatorChoosesForceLandGtConvoyLandForce ==
    /\ mayorState = Observing
    /\ mayorState' = ForceLanding
    /\ UNCHANGED <<launchChannel, landChannel, convoy_doneChannel>>

\* (NormalLanding, mayor sends Land to convoy, Done)
Mayor_MayorSendsLandToConvoy ==
    /\ mayorState = NormalLanding
    /\ mayorState' = Done
    /\ landChannel \in {Ch_NotSent, Ch_Delivered}
    /\ landChannel' = Land
    /\ UNCHANGED <<launchChannel, convoy_doneChannel>>

\* (ForceLanding, mayor sends ForceLand to convoy (--force bypasses AllDone), Done)
Mayor_MayorSendsForceLandToConvoyForceBypassesAllDone ==
    /\ mayorState = ForceLanding
    /\ mayorState' = Done
    /\ landChannel \in {Ch_NotSent, Ch_Delivered}
    /\ landChannel' = ForceLand
    /\ UNCHANGED <<launchChannel, convoy_doneChannel>>

\* (Done, terminal, Done)
Mayor_Terminal ==
    /\ mayorState = Done
    /\ mayorState' = Done
    /\ UNCHANGED <<launchChannel, landChannel, convoy_doneChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Mayor_MayorLaunchesTheConvoy
    \/ Mayor_LaunchSentMayorObserves
    \/ Mayor_ConvoyReportsCompleteMayorPreparesNormalLand
    \/ Mayor_OperatorChoosesForceLandGtConvoyLandForce
    \/ Mayor_MayorSendsLandToConvoy
    \/ Mayor_MayorSendsForceLandToConvoyForceBypassesAllDone
    \/ Mayor_Terminal

====
