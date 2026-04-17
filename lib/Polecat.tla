---- MODULE Polecat ----
(*
@kinner {
  "component": "Polecat",
  "version": "0.2.1",
  "description": "Polecat agent. Option C: both SLING-receive and observe-driven paths to Working.",
  "ports": {
    "SLING": {
      "direction": "in",
      "variable": "slingChannel",
      "description": "receives a sling assignment from Feeder."
    },
    "MERGE_READY": {
      "direction": "out",
      "variable": "merge_readyChannel",
      "description": "signals the refinery that work is complete (done.go:1170 nudgeRefinery). Tagged 'MergeReady'."
    },
    "HOOK_IN": {
      "direction": "in",
      "variable": "hook_inChannel",
      "description": "receives a Claude Code session lifecycle event (PreCompact, etc.)."
    },
    "ISSUE_OBSERVE": {
      "direction": "observe",
      "variable": "issueState",
      "states": [
        "Open",
        "Hooked",
        "InProgress",
        "Closed"
      ],
      "description": "observes the assigned Issue's state."
    }
  },
  "variables": {
    "state": "polecatState",
    "slingChannel": "slingChannel",
    "merge_readyChannel": "merge_readyChannel",
    "hook_inChannel": "hook_inChannel",
    "ISSUE_OBSERVE": "issueState"
  },
  "stateConstants": [
    "Absent",
    "Working",
    "HandlingHook",
    "Done",
    "Idle"
  ],
  "tagConstants": [
    "MergeReady",
    "PreCompact",
    "Sling"
  ]
}
*)

EXTENDS Integers, TLC

\* -- CONSTANTS ----------------------------------------------------------------
CONSTANTS
    Absent,
    Working,
    HandlingHook,
    Done,
    Idle,
    ISSUE_OBSERVE_Open,
    ISSUE_OBSERVE_Hooked,
    ISSUE_OBSERVE_InProgress,
    ISSUE_OBSERVE_Closed,
    Ch_NotSent,
    Ch_InFlight,
    Ch_Delivered,
    MergeReady,
    PreCompact,
    Sling

\* -- VARIABLES ----------------------------------------------------------------
VARIABLES
    polecatState,
    issueState,
    slingChannel,
    merge_readyChannel,
    hook_inChannel

\* -- TYPE INVARIANT -----------------------------------------------------------
TypeInvariant ==
    /\ polecatState \in {Absent, Working, HandlingHook, Done, Idle}
    /\ slingChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {MergeReady, PreCompact, Sling}
    /\ merge_readyChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {MergeReady, PreCompact, Sling}
    /\ hook_inChannel \in {Ch_NotSent, Ch_InFlight, Ch_Delivered} \union {MergeReady, PreCompact, Sling}

\* -- INITIAL STATE ------------------------------------------------------------
Init ==
    /\ polecatState = Absent

\* -- ACTIONS ------------------------------------------------------------------
\* (Absent, polecat receives sling assignment (channel-driven path), Working)
Polecat_PolecatReceivesSlingAssignmentChannelDrivenPath ==
    /\ polecatState = Absent
    /\ slingChannel = Sling
    /\ issueState = ISSUE_OBSERVE_Hooked
    /\ polecatState' = Working
    /\ slingChannel' = Ch_Delivered
    /\ UNCHANGED <<issueState, merge_readyChannel, hook_inChannel>>

\* (Absent, polecat advances by observing its assigned issue is hooked (observe-driven path), Working)
Polecat_PolecatAdvancesByObservingItsAssignedIssueIsHookedObserveDrivenPath ==
    /\ polecatState = Absent
    /\ issueState = ISSUE_OBSERVE_Hooked
    /\ polecatState' = Working
    /\ UNCHANGED <<issueState, slingChannel, merge_readyChannel, hook_inChannel>>

\* (Working, work complete: signal refinery, Done)
Polecat_WorkCompleteSignalRefinery ==
    /\ polecatState = Working
    /\ issueState = ISSUE_OBSERVE_InProgress \/ issueState = ISSUE_OBSERVE_Closed
    /\ polecatState' = Done
    /\ merge_readyChannel \in {Ch_NotSent, Ch_Delivered}
    /\ merge_readyChannel' = MergeReady
    /\ UNCHANGED <<issueState, slingChannel, hook_inChannel>>

\* (Done, agent state transitions to idle, Idle)
Polecat_AgentStateTransitionsToIdle ==
    /\ polecatState = Done
    /\ issueState = ISSUE_OBSERVE_Closed
    /\ polecatState' = Idle
    /\ UNCHANGED <<issueState, slingChannel, merge_readyChannel, hook_inChannel>>

\* (Idle, terminal, Idle)
Polecat_Terminal ==
    /\ polecatState = Idle
    /\ polecatState' = Idle
    /\ UNCHANGED <<issueState, slingChannel, merge_readyChannel, hook_inChannel>>

\* (Working, polecat receives PreCompact lifecycle event (substrate-layer), HandlingHook)
Polecat_PolecatReceivesPreCompactLifecycleEventSubstrateLayer ==
    /\ polecatState = Working
    /\ hook_inChannel = PreCompact
    /\ polecatState' = HandlingHook
    /\ hook_inChannel' = Ch_Delivered
    /\ UNCHANGED <<issueState, slingChannel, merge_readyChannel>>

\* (HandlingHook, hook handler completes; headless polecat returns to working, Working)
Polecat_HookHandlerCompletesHeadlessPolecatReturnsToWorking ==
    /\ polecatState = HandlingHook
    /\ polecatState' = Working
    /\ UNCHANGED <<issueState, slingChannel, merge_readyChannel, hook_inChannel>>

\* -- NEXT STATE RELATION ------------------------------------------------------
Next ==
       Polecat_PolecatReceivesSlingAssignmentChannelDrivenPath
    \/ Polecat_PolecatAdvancesByObservingItsAssignedIssueIsHookedObserveDrivenPath
    \/ Polecat_WorkCompleteSignalRefinery
    \/ Polecat_AgentStateTransitionsToIdle
    \/ Polecat_Terminal
    \/ Polecat_PolecatReceivesPreCompactLifecycleEventSubstrateLayer
    \/ Polecat_HookHandlerCompletesHeadlessPolecatReturnsToWorking

====
