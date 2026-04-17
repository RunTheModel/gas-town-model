---- MODULE Hook ----
(*
@kinner {
  "component": "Hook",
  "version": "0.1.0",
  "description": "Lifecycle event firer. Real implementation: internal/hooks/config.go (type Hook). Each Hook instance fires once when its lifecycle moment is reached; the bound agent receives the event via the AGENT port and is responsible for handling. Generalization to multiple hook types and multi-fire (a single hook firing many times across an agent's lifetime) is deferred -- this is the simplest shape that captures the boundary.",
  "ports": {
    "AGENT": {
      "direction": "out",
      "variable": "agentChannel",
      "description": "fires the hook event at the bound agent (the Claude session targeted by this hook). Tagged with 'PreCompact' so the bound receiver can pattern-match on this specific lifecycle event."
    }
  },
  "variables": {
    "state": "hookState",
    "agentChannel": "agentChannel"
  },
  "stateConstants": [
    "Idle",
    "Fired"
  ],
  "tagConstants": [
    "PreCompact"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Idle,
    Fired,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    PreCompact

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    hookState,
    agentChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ hookState \in {Idle, Fired}
    /\ agentChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {PreCompact}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ hookState = Idle

\* -- ACTIONS ------------------------------------------------------------------
\* (Idle, lifecycle moment reached: PreCompact fires, Fired)
Hook_LifecycleMomentReachedPreCompactFires ==
    /\ hookState = Idle
    /\ hookState' = Fired
    /\ agentChannel \in {Ch_NotSent, Ch_Delivered}
    /\ agentChannel' = PreCompact

\* (Fired, terminal: hook fires exactly once per lifecycle moment, Fired)
Hook_TerminalHookFiresExactlyOncePerLifecycleMoment ==
    /\ hookState = Fired
    /\ hookState' = Fired
    /\ UNCHANGED <<agentChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Hook_LifecycleMomentReachedPreCompactFires
    \/ Hook_TerminalHookFiresExactlyOncePerLifecycleMoment

====
