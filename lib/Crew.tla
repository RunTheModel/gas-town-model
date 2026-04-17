---- MODULE Crew ----
(*
@kinner {
  "component": "Crew",
  "version": "0.1.0",
  "description": "A crew member. Absent until created; Created forever after. The persistence-across-WorkSource-cycles property is captured by the lack of any Created -> Absent transition.",
  "ports": {
    "CREATE": {
      "direction": "in",
      "variable": "createChannel",
      "description": "receives a creation signal that brings the crew into existence. Tagged 'Create'. Once received, no further transitions."
    }
  },
  "variables": {
    "state": "crewState",
    "createChannel": "createChannel"
  },
  "stateConstants": [
    "Absent",
    "Created"
  ],
  "tagConstants": [
    "Create"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Absent,
    Created,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    Create

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    crewState,
    createChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ crewState \in {Absent, Created}
    /\ createChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Create}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ crewState = Absent

\* -- ACTIONS ------------------------------------------------------------------
\* (Absent, crew created (e.g., gt crew add), Created)
Crew_CrewCreatedEGGtCrewAdd ==
    /\ crewState = Absent
    /\ createChannel = Create
    /\ crewState' = Created
    /\ createChannel' = Ch_Delivered

\* (Created, terminal: crew persists forever once created, Created)
Crew_TerminalCrewPersistsForeverOnceCreated ==
    /\ crewState = Created
    /\ crewState' = Created
    /\ UNCHANGED <<createChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Crew_CrewCreatedEGGtCrewAdd
    \/ Crew_TerminalCrewPersistsForeverOnceCreated

====
