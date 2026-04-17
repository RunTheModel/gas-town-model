---- MODULE Dog ----
(*
@kinner {
  "component": "Dog",
  "version": "0.1.0",
  "description": "Infrastructure worker. Idle = available for assignment. Working = handling an assigned plugin task. Returns to Idle on Clear. Doesn't model the work itself (that's plugin-specific); just the lifecycle state.",
  "ports": {
    "ASSIGN": {
      "direction": "in",
      "variable": "assignChannel",
      "description": "receives an assignment from the Deacon to handle a plugin task. Tagged 'Assign'."
    },
    "CLEAR": {
      "direction": "in",
      "variable": "clearChannel",
      "description": "receives a clear signal from the Deacon when work is done or the dog should be freed. Tagged 'Clear'."
    }
  },
  "variables": {
    "state": "dogState",
    "assignChannel": "assignChannel",
    "clearChannel": "clearChannel"
  },
  "stateConstants": [
    "Idle",
    "Working"
  ],
  "tagConstants": [
    "Assign",
    "Clear"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Idle,
    Working,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    Assign,
    Clear

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    dogState,
    assignChannel,
    clearChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ dogState \in {Idle, Working}
    /\ assignChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Assign, Clear}
    /\ clearChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Assign, Clear}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ dogState = Idle

\* -- ACTIONS ------------------------------------------------------------------
\* (Idle, deacon assigns plugin work to dog, Working)
Dog_DeaconAssignsPluginWorkToDog ==
    /\ dogState = Idle
    /\ assignChannel = Assign
    /\ dogState' = Working
    /\ assignChannel' = Ch_Delivered
    /\ UNCHANGED <<clearChannel>>

\* (Working, deacon clears the dog (work complete or dog freed), Idle)
Dog_DeaconClearsTheDogWorkCompleteOrDogFreed ==
    /\ dogState = Working
    /\ clearChannel = Clear
    /\ dogState' = Idle
    /\ clearChannel' = Ch_Delivered
    /\ UNCHANGED <<assignChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Dog_DeaconAssignsPluginWorkToDog
    \/ Dog_DeaconClearsTheDogWorkCompleteOrDogFreed

====
