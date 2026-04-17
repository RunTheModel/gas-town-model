---- MODULE Worktree ----
(*
@kinner {
  "component": "Worktree",
  "version": "0.1.0",
  "description": "On-disk worktree directory. Present after polecat spawn (initial state, since this component does not yet model the spawn step). Cleaned after Landing's CLEAN signal -- corresponds to removePolecatWorktree in cmd/convoy.go:1243-1255.",
  "ports": {
    "CLEAN": {
      "direction": "in",
      "variable": "cleanChannel",
      "description": "receives a clean signal from the Landing actor when the convoy lands. Tagged 'Clean'."
    }
  },
  "variables": {
    "state": "worktreeState",
    "cleanChannel": "cleanChannel"
  },
  "stateConstants": [
    "Present",
    "Cleaned"
  ],
  "tagConstants": [
    "Clean"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Present,
    Cleaned,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    Clean

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    worktreeState,
    cleanChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ worktreeState \in {Present, Cleaned}
    /\ cleanChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {Clean}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ worktreeState = Present

\* -- ACTIONS ------------------------------------------------------------------
\* (Present, Landing fires CLEAN: worktree directory removed, Cleaned)
Worktree_LandingFiresCLEANWorktreeDirectoryRemoved ==
    /\ worktreeState = Present
    /\ cleanChannel = Clean
    /\ worktreeState' = Cleaned
    /\ cleanChannel' = Ch_Delivered

\* (Cleaned, terminal, Cleaned)
Worktree_Terminal ==
    /\ worktreeState = Cleaned
    /\ worktreeState' = Cleaned
    /\ UNCHANGED <<cleanChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Worktree_LandingFiresCLEANWorktreeDirectoryRemoved
    \/ Worktree_Terminal

====
