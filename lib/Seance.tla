---- MODULE Seance ----
(*
@kinner {
  "component": "Seance",
  "version": "0.1.0",
  "description": "Question responder. Pending = waiting for a query. Looking = consulting internal context (the lookup itself isn't modeled at this level). Answering = emitting the response. Returns to Pending so the same Seance can answer multiple queries in sequence.",
  "ports": {
    "QUERY": {
      "direction": "in",
      "variable": "queryChannel",
      "description": "receives a query that needs answering. Tagged 'Query'."
    },
    "ANSWER": {
      "direction": "out",
      "variable": "answerChannel",
      "description": "emits the answer back to the querying actor. Tagged 'Answer'."
    }
  },
  "variables": {
    "state": "seanceState",
    "queryChannel": "queryChannel",
    "answerChannel": "answerChannel"
  },
  "stateConstants": [
    "Pending",
    "Looking",
    "Answering"
  ],
  "tagConstants": [
    "Answer",
    "Query"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Pending,
    Looking,
    Answering,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    Answer,
    Query

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    seanceState,
    queryChannel,
    answerChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ seanceState \in {Pending, Looking, Answering}
    /\ queryChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Answer, Query}
    /\ answerChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Answer, Query}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ seanceState = Pending

\* -- ACTIONS ------------------------------------------------------------------
\* (Pending, receives a query, Looking)
Seance_ReceivesAQuery ==
    /\ seanceState = Pending
    /\ queryChannel = Query
    /\ seanceState' = Looking
    /\ queryChannel' = Ch_Delivered
    /\ UNCHANGED <<answerChannel>>

\* (Looking, consultation complete (lookup not modeled at this level), Answering)
Seance_ConsultationCompleteLookupNotModeledAtThisLevel ==
    /\ seanceState = Looking
    /\ seanceState' = Answering
    /\ UNCHANGED <<queryChannel, answerChannel>>

\* (Answering, emit the answer, Pending)
Seance_EmitTheAnswer ==
    /\ seanceState = Answering
    /\ seanceState' = Pending
    /\ answerChannel \in {Ch_NotSent, Ch_Delivered}
    /\ answerChannel' = Answer
    /\ UNCHANGED <<queryChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Seance_ReceivesAQuery
    \/ Seance_ConsultationCompleteLookupNotModeledAtThisLevel
    \/ Seance_EmitTheAnswer

====
