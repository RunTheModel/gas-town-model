"""
kinner_runtime: minimal runtime for the hand-designed Python target.

Implements the contract established across:
  - design/python-target/invariants.md
  - design/python-target/asymmetries.md
  - design/python-target/transitions.md

Design goal: every method reads top-to-bottom as a straight sequence.
No closures over mutable state, no clever tricks, no hidden dispatch.
This file gets scrutinized for TLC-vs-Python fidelity; it earns that
scrutiny by being obvious at a glance.

Claim: if every transition fires atomically, guards read current
state directly, and hooks run post-commit, then the transition
relation the simulator produces matches TLA+'s. TLC's safety and
liveness proofs transfer to this runtime's runs.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------


class DisabledActionError(Exception):
    """Raised when `fire()` is called with a disabled action. Carries
    the action name, component state, and reason so a trace script
    sees exactly where it diverged from the spec."""

    def __init__(self, qualified_name: str, component_state: str, reason: str):
        super().__init__(
            f"action {qualified_name!r} not enabled "
            f"(current state {component_state!r}): {reason}"
        )
        self.qualified_name = qualified_name
        self.component_state = component_state
        self.reason = reason


class InvariantViolation(Exception):
    """Raised when a registered invariant fails evaluation. Carries
    the invariant id, a readable state summary, and the action name
    that led to the violating state."""

    def __init__(self, inv_id: str, state_summary: str, last_action: str | None):
        super().__init__(
            f"invariant {inv_id!r} violated after "
            f"{last_action or 'init'}: {state_summary}"
        )
        self.inv_id = inv_id
        self.state_summary = state_summary
        self.last_action = last_action


class MessageSetViolation(Exception):
    """Raised when a send or raise applies a tag outside the
    sender's declared MessageSet (class attr `_message_set`
    populated from the manifest's `tag_constants`).

    TLA+ rejects the same state via TypeInvariant / `\\in MessageSet`
    guards; Python raises at apply time so the offending transition
    is visible at the call site. Untyped components (empty
    `_message_set`) never raise.
    """

    def __init__(self, component_alias: str, port: str, tag: str,
                 allowed: frozenset):
        super().__init__(
            f"component {component_alias!r} sent tag {tag!r} on "
            f"port {port!r} which is not in its declared MessageSet "
            f"{sorted(allowed)!r}"
        )
        self.component_alias = component_alias
        self.port = port
        self.tag = tag
        self.allowed = allowed


class ReplayDivergence(Exception):
    """Raised by `Application.replay(trace)` when Python's post-state
    differs from the trace's recorded post-state. Identifies the
    exact step and the per-variable diffs."""

    def __init__(self, step: int, action: str | None, diffs: dict[str, tuple]):
        diff_summary = ", ".join(
            f"{k}: expected {exp!r}, got {act!r}"
            for k, (exp, act) in diffs.items()
        )
        super().__init__(
            f"replay diverged at step {step} "
            f"({action or 'init'}): {diff_summary}"
        )
        self.step = step
        self.action = action
        self.diffs = diffs


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Transition:
    """Static description of a component transition. Emitted by the
    code generator inside each Component's `_build_transitions()`.

    A transition can combine up to three channel effects in one
    atomic step (backlog/076): receive + send + raise. All fire
    together or not at all. Optional counter increment.
    """

    name: str
    from_state: str
    to_state: str
    kind: str           # "local" | "send" | "receive" | "send_receive"
    send_port: str | None = None
    send_tag: str | None = None
    recv_port: str | None = None
    recv_tag: str | None = None
    raise_port: str | None = None
    raise_tag: str | None = None
    guard_fn: Callable[[Any], bool] | None = None
    effect_fn: Callable[[Any], None] | None = None
    counter_increment: str | None = None
    assigns: tuple[tuple[str, Callable[[Any], Any]], ...] = ()
    """Backlog 134: typed-variable assignments fired atomically with the
    transition. Each entry is `(var_name, value_fn)` where `value_fn`
    takes the component instance and returns the new value. Applied in
    order via `setattr(comp, var_name, value_fn(comp))` after channel
    effects and before user `effect_fn`. Empty for triples in the
    legacy increment shape."""
    forward_capture: bool = False
    """When True, the receive step stashes the incoming channel's tag
    into `self._msg_in_flight`. Mirrors TLA+'s `_msgInFlight' = chan`
    capture pattern used by tagless-forwarding library components like
    MessageQueue. Backlog 119."""
    forward_send: bool = False
    """When True, the send step uses `self._msg_in_flight` as the
    outgoing tag instead of `send_tag`. Mirrors TLA+'s
    `chan' = _msgInFlight` forwarding send. Pairs with
    `forward_capture` on the same component: one receive captures,
    later send forwards. Backlog 119."""


@dataclass
class Channel:
    """Runtime state of a tagged channel binding. One instance per
    out->in port pair; both endpoints mutate this object directly.
    State progression: NotSent -> InFlight -> Delivered."""

    name: str = ""
    state: str = "NotSent"
    tag: str | None = None

    def snapshot(self) -> tuple[str, str | None]:
        return (self.state, self.tag)

    def restore(self, snap: tuple[str, str | None]) -> None:
        self.state, self.tag = snap


@dataclass(frozen=True)
class TransitionEvent:
    """Hook payload. Carries everything a hook needs to react --
    action name, component alias, from/to state, optional tag."""

    qualified_name: str
    action_name: str
    component_alias: str
    from_state: str
    to_state: str
    tag: str | None = None


# ---------------------------------------------------------------------------
# Synthesized actions (fan-out, fan-in)
#
# Each subclass carries exactly the data it needs to check `is_enabled`
# and perform `apply`. No closures, no late-binding traps. A reviewer
# can read each class in under 15 lines and know what fires.
# ---------------------------------------------------------------------------


class SynthAction:
    """Application-level action synthesized at bind time. Fires like
    a transition but belongs to no component."""

    name: str

    def is_enabled(self) -> bool:
        raise NotImplementedError

    def apply(self) -> None:
        raise NotImplementedError


class FanOut(SynthAction):
    """Broadcast one sender's InFlight message to N receiver channels
    atomically. Source becomes Delivered; each target becomes InFlight
    with the same tag."""

    def __init__(self, name: str, source: Channel, targets: list[Channel]):
        self.name = name
        self.source = source
        self.targets = targets

    def is_enabled(self) -> bool:
        if self.source.state != "InFlight":
            return False
        return all(t.state in ("NotSent", "Delivered") for t in self.targets)

    def apply(self) -> None:
        tag = self.source.tag
        for t in self.targets:
            t.tag = tag
            t.state = "InFlight"
        self.source.state = "Delivered"


class FanInMerge(SynthAction):
    """Merge one source into the shared destination. Source becomes
    Delivered; destination becomes InFlight with the source's tag.
    One such action exists per sender in a fan-in group."""

    def __init__(self, name: str, source: Channel, dest: Channel):
        self.name = name
        self.source = source
        self.dest = dest

    def is_enabled(self) -> bool:
        return (
            self.source.state == "InFlight"
            and self.dest.state in ("NotSent", "Delivered")
        )

    def apply(self) -> None:
        self.dest.tag = self.source.tag
        self.dest.state = "InFlight"
        self.source.state = "Delivered"


# ---------------------------------------------------------------------------
# Buffered ports (backlog 077)
#
# A composite MODULE can declare `bufferDepth` on an external port.
# The port's external surface is unchanged -- it still appears in the
# composite's `_in_ports` or `_out_ports` and callers bind it via
# `_channel` like any other port. What differs is internal: instead
# of forwarding to the sub-component's port, the composite interposes
# a bounded Seq buffer between the external channel and the sub-
# component's channel. Two synthesized actions per buffer move
# messages: enqueue (source channel -> buffer) and dequeue (buffer ->
# target channel). Depth is a per-buffer cap; enqueue is disabled
# when `len(items) >= depth`, matching TLA+'s `Len(buf) < bound`.
# ---------------------------------------------------------------------------


@dataclass
class Buffer:
    """FIFO message buffer for a composite's buffered port. Owned by
    the composite instance; snapshotted by the Application. A buffer
    has fixed `depth` (set in the composite's __init__) and a list of
    tags (`items`). Enqueue appends to the tail; dequeue pops from
    the head. Class-attribute membership of the associated port in
    `_in_ports`/`_out_ports` is unchanged -- only internal wiring
    differs between a buffered and a non-buffered port."""

    name: str = ""
    depth: int = 0
    items: list = field(default_factory=list)

    def snapshot(self) -> tuple[int, tuple]:
        return (self.depth, tuple(self.items))

    def restore(self, snap: tuple[int, tuple]) -> None:
        depth, items = snap
        self.depth = depth
        self.items = list(items)


class BufferEnqueue(SynthAction):
    """Enqueue action: when the source channel is InFlight AND the
    buffer has room, append the source's tag to the buffer and mark
    the source Delivered. Matches TLA+'s synthesized Enqueue action
    body exactly (see PeekLockQueue.tla backlog 077).

    Source is resolved lazily via `(component, port)` lookup on
    `_port_channels` at fire time. This lets external callers bind
    the composite's port any time before firing -- init order is
    irrelevant."""

    def __init__(
        self,
        name: str,
        source_comp: "Component",
        source_port: str,
        buffer: Buffer,
    ):
        self.name = name
        self.source_comp = source_comp
        self.source_port = source_port
        self.buffer = buffer

    def _source(self) -> Channel | None:
        return self.source_comp._port_channels.get(self.source_port)

    def is_enabled(self) -> bool:
        src = self._source()
        if src is None:
            return False
        return (
            src.state == "InFlight"
            and len(self.buffer.items) < self.buffer.depth
        )

    def apply(self) -> None:
        src = self._source()
        assert src is not None, (
            f"{self.name}: source channel disappeared between "
            f"is_enabled and apply"
        )
        self.buffer.items.append(src.tag)
        src.state = "Delivered"


class BufferDequeue(SynthAction):
    """Dequeue action: when the buffer is non-empty AND the target
    channel is clear (NotSent or Delivered), pop the head tag into
    the target as InFlight.

    Target is resolved lazily via `(component, port)` lookup on
    `_port_channels` at fire time."""

    def __init__(
        self,
        name: str,
        buffer: Buffer,
        target_comp: "Component",
        target_port: str,
    ):
        self.name = name
        self.buffer = buffer
        self.target_comp = target_comp
        self.target_port = target_port

    def _target(self) -> Channel | None:
        return self.target_comp._port_channels.get(self.target_port)

    def is_enabled(self) -> bool:
        tgt = self._target()
        if tgt is None:
            return False
        return (
            len(self.buffer.items) > 0
            and tgt.state in ("NotSent", "Delivered")
        )

    def apply(self) -> None:
        tgt = self._target()
        assert tgt is not None, (
            f"{self.name}: target channel disappeared between "
            f"is_enabled and apply"
        )
        tgt.tag = self.buffer.items.pop(0)
        tgt.state = "InFlight"


class FanOutBufferAppend(SynthAction):
    """Atomic N-way buffered enqueue (backlog 074.1 + 103). When the
    source channel is InFlight AND every target buffer has room,
    append the source's tag to each buffer and mark the source
    Delivered. Matches TLA+'s `FanOutAppend` action exactly:
    one publisher, N per-subscriber Seq buffers, one atomic step.

    The per-subscriber `DrainAction` (rendered as `BufferDequeue` in
    Python) fires independently and pops each buffer into its
    subscriber's input channel. Source resolved lazily via
    `(component, port)` lookup so binding order is irrelevant.
    """

    def __init__(
        self,
        name: str,
        source_comp: "Component",
        source_port: str,
        buffers: list[Buffer],
    ):
        self.name = name
        self.source_comp = source_comp
        self.source_port = source_port
        self.buffers = buffers

    def _source(self) -> Channel | None:
        return self.source_comp._port_channels.get(self.source_port)

    def is_enabled(self) -> bool:
        src = self._source()
        if src is None:
            return False
        if src.state != "InFlight":
            return False
        return all(len(b.items) < b.depth for b in self.buffers)

    def apply(self) -> None:
        src = self._source()
        assert src is not None, (
            f"{self.name}: source channel disappeared between "
            f"is_enabled and apply"
        )
        for b in self.buffers:
            b.items.append(src.tag)
        src.state = "Delivered"


# ---------------------------------------------------------------------------
# Component base class
# ---------------------------------------------------------------------------


class Component:
    """Base class for every generated component. Subclasses declare:

      - `initial_state`: str
      - `state_constants`: tuple of state names
      - `_in_ports` / `_out_ports` / `_observe_ports`: tuples
      - `_counter_defaults`: {name: initial_value}

    and implement `_build_transitions() -> list[Transition]`.
    """

    initial_state: str = ""
    state_constants: tuple[str, ...] = ()
    _in_ports: tuple[str, ...] = ()
    _out_ports: tuple[str, ...] = ()
    _observe_ports: tuple[str, ...] = ()
    _counter_defaults: dict[str, int] = {}
    # Option defaults from the manifest. Instance __init__ seeds
    # self._options = dict(_option_defaults); per-instance overrides
    # merge via **kwargs at construction time. Guards translate
    # CONSTANT references (the option name) to self._options[name]
    # so bound-checking transitions like `count < maxWrites` resolve
    # at runtime.
    _option_defaults: dict[str, Any] = {}
    # CONSTANT name -> option name reverse map. Parent composites
    # and APP codegen pass option overrides via the CONSTANT name
    # found in `ComponentInstance.with_mappings` (the same path TLA+
    # uses for its INSTANCE ... WITH clause). __init__ translates
    # each CONSTANT-name kwarg to its option-name key via this dict.
    # Emitted by leaf codegen from `manifest.options[name].constant`.
    _option_constants: dict[str, str] = {}
    # Backlog 134: typed actor variables -- name -> default value.
    # __init__ seeds each as an instance attribute; transitions with
    # `assigns` mutate them via `setattr(comp, name, value_fn(comp))`.
    # Distinct from `_counter_defaults` (which is a `_counters` dict
    # keyed by name) -- typed vars are first-class instance attrs so
    # generated code can write `self.n` directly.
    _typed_var_defaults: dict[str, Any] = {}
    # Allowed tag values for sends + raises. Emitted by leaf
    # codegen from `manifest.tag_constants` -- the same IR field
    # TLA+ reads to emit TypeInvariant `chan \\in ... \\union
    # MessageSet`. Empty set means untyped: the component predates
    # tagConstants or opts out, and any tag (including None) is
    # accepted. Runtime _apply enforces on non-None send_tag /
    # raise_tag against a non-empty set. See MessageSetViolation.
    _message_set: frozenset = frozenset()

    def __init__(self, **kwargs: Any) -> None:
        self.state: str = self.initial_state
        self._counters: dict[str, int] = dict(self._counter_defaults)
        self._options: dict[str, Any] = dict(self._option_defaults)
        # Backlog 148: merge kwargs into self._options BEFORE seeding
        # typed-var attrs so option-name defaults can read the resolved
        # option value (post-override). Pre-148 ordering seeded typed
        # vars first; harmless when defaults were always int literals.
        for k, v in kwargs.items():
            # Kwargs may arrive keyed by option name (direct user
            # overrides) or CONSTANT name (parent composite / APP
            # codegen mirroring TLA+'s WITH clause).
            if k in self._option_defaults:
                option_name = k
            elif k in self._option_constants:
                option_name = self._option_constants[k]
            else:
                raise TypeError(
                    f"{type(self).__name__}() got unexpected kwarg "
                    f"{k!r}; known options: {list(self._option_defaults)}; "
                    f"known CONSTANT aliases: {list(self._option_constants)}"
                )
            self._options[option_name] = v
        # Seed typed-var attrs. int default => set directly; str default
        # (backlog 148) names an option, look up the resolved value.
        for _tv_name, _tv_default in self._typed_var_defaults.items():
            if isinstance(_tv_default, str):
                setattr(self, _tv_name, self._options[_tv_default])
            else:
                setattr(self, _tv_name, _tv_default)
        self._port_channels: dict[str, Channel] = {}
        self._observed: dict[str, Component] = {}
        self._msg_in_flight: str | None = None
        """MODULE tag-forwarding slot. Receives with forward_capture
        stash the incoming channel's tag here; later PORT_FORWARD
        sends read it back out. Mirrors TLA+'s _msgInFlight variable.
        Backlog 119."""
        self._transitions: list[Transition] = self._build_transitions()
        self._app: Application | None = None
        self._alias: str = ""

    def _build_transitions(self) -> list[Transition]:
        raise NotImplementedError

    def patch(self, **updates: Any) -> None:
        """Hot-patch state and/or counters. Explicit escape hatch
        from the verified transition relation. Validates names so
        typos fail loud."""
        if "state" in updates:
            new_state = updates.pop("state")
            if new_state not in self.state_constants:
                raise ValueError(
                    f"patch: {new_state!r} not in {self._alias}'s "
                    f"state_constants {self.state_constants}"
                )
            self.state = new_state
        for key, val in updates.items():
            if key not in self._counter_defaults:
                raise ValueError(
                    f"patch: unknown field {key!r} on {self._alias} "
                    f"(counters: {list(self._counter_defaults)})"
                )
            self._counters[key] = int(val)


# ---------------------------------------------------------------------------
# Application base class
#
# Organized into sections, each a self-contained responsibility:
#   - Registration / binding
#   - Enabled-set enumeration
#   - Fire (explicit) / step (scheduler)
#   - Atomic commit phases (apply -> hooks -> invariants)
#   - Hook dispatch
#   - Snapshot / restore / replay
# ---------------------------------------------------------------------------


class Application:
    """Base class for every generated Application."""

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed
        self._rng = random.Random(seed)
        self._components: dict[str, Component] = {}
        self._channels: list[Channel] = []
        self._buffers: list[Buffer] = []
        self._synth_actions: list[SynthAction] = []
        self._invariants: list[tuple[str, Callable[[Application], bool]]] = []
        self._last_action: str | None = None

    # ----- Registration / binding ---------------------------------

    def _register(self, alias: str, component: Component) -> None:
        """Register a component under `alias`, handling composites.

        Two-pass contract:

          Pass 1: walk the composite tree and register every
                  component in `_components` before any internal
                  bindings replay. That way fan-in / fan-out /
                  channel / observe calls in the bindings can
                  reference any sub-component by reference without
                  worrying about registration order.

          Pass 2: walk the same tree and replay each composite's
                  `_internal_bindings` via the standard _channel /
                  _observe / _fanout / _fanin API. Bindings from
                  deeper composites replay first (post-order) so
                  any reference to an already-registered leaf
                  resolves cleanly.

        Compound alias collisions (e.g. `O.Mid.Leaf` and `O_Mid.Leaf`
        both normalizing to `O_Mid_Leaf` for hook dispatch) raise
        immediately.
        """
        self._register_tree(alias, component)
        self._replay_bindings_tree(component)

    def _register_tree(self, alias: str, component: Component) -> None:
        """Pass 1: register `component` and recurse into its
        `_sub_components` with compound aliases. Does not apply
        internal bindings."""
        if alias in self._components:
            raise ValueError(
                f"alias {alias!r} already registered"
            )
        # Compound-alias hook-name collision check. "O.Mid.Leaf" and
        # "O_Mid.Leaf" both normalize to "O_Mid_Leaf"; that would
        # collide in hook dispatch. Very unlikely with typical
        # CamelCase aliases, but cheap to catch.
        normalized = alias.replace(".", "_")
        for existing in self._components:
            if existing.replace(".", "_") == normalized and existing != alias:
                raise ValueError(
                    f"alias {alias!r} normalizes to hook-name "
                    f"{normalized!r} which collides with already-"
                    f"registered alias {existing!r}"
                )
        self._components[alias] = component
        component._app = self
        component._alias = alias
        for sub_suffix, sub_comp in (
            getattr(component, "_sub_components", {}) or {}
        ).items():
            self._register_tree(f"{alias}.{sub_suffix}", sub_comp)

    def _replay_bindings_tree(self, component: Component) -> None:
        """Pass 2: depth-first replay of `_internal_bindings`.
        Deepest composites bind first; outer composites bind after
        their sub-trees are wired up."""
        for sub_comp in (
            getattr(component, "_sub_components", {}) or {}
        ).values():
            self._replay_bindings_tree(sub_comp)
        for binding in getattr(component, "_internal_bindings", ()) or ():
            kind = binding["kind"]
            if kind == "channel":
                self._channel(
                    binding["a_comp"], binding["a_port"],
                    binding["b_comp"], binding["b_port"],
                )
            elif kind == "observe":
                self._observe(
                    binding["observer"], binding["port"],
                    binding["target"],
                )
            elif kind == "fan":
                # Direction-agnostic fan. Runtime dispatches to
                # _fanout vs _fanin via class-attr port directions.
                self._fan(binding["endpoints"], owner=component)
            elif kind == "invariant":
                # Composite MODULE invariants register with the
                # outer Application the same way Application-level
                # invariants do. Predicate takes `app` and reads
                # state through app._components lookups.
                self._register_invariant(
                    binding["id"], binding["predicate"],
                )
            elif kind == "buffer":
                # Register a Buffer (already constructed in the
                # composite's __init__ under self._buffers_by_name)
                # with the Application for snapshot/restore. Runs
                # before buffer_enqueue / buffer_dequeue bindings so
                # those can reference it by name.
                buf = component._buffers_by_name[binding["name"]]
                self._buffers.append(buf)
            elif kind == "internal_channel":
                # Allocate a Channel for a sub-component's internal-
                # only port (one endpoint of a buffered path). The
                # port is in the sub's _in_ports/_out_ports but no
                # external caller binds it -- the buffer interposes.
                sub = component._sub_components[binding["sub"]]
                port = binding["port"]
                ch = Channel(
                    name=f"{sub._alias}.{port}"
                )
                sub._port_channels[port] = ch
                self._channels.append(ch)
            elif kind == "buffer_enqueue":
                # Synthesize an enqueue action from (source port) to
                # (buffer). `source` is (alias, port); alias="" means
                # the composite itself, otherwise a sub-component of
                # this composite. Resolved to Component references
                # now; the SynthAction looks up the Channel lazily.
                source_comp = _resolve_endpoint(
                    component, binding["source"],
                )
                buf = component._buffers_by_name[binding["buffer"]]
                synth = BufferEnqueue(
                    binding["action"],
                    source_comp, binding["source"][1],
                    buf,
                )
                synth.component = component
                self._synth_actions.append(synth)
            elif kind == "buffer_dequeue":
                # Synthesize a dequeue action from (buffer) to
                # (target port). Same endpoint convention as
                # buffer_enqueue.
                buf = component._buffers_by_name[binding["buffer"]]
                target_comp = _resolve_endpoint(
                    component, binding["target"],
                )
                synth = BufferDequeue(
                    binding["action"],
                    buf,
                    target_comp, binding["target"][1],
                )
                synth.component = component
                self._synth_actions.append(synth)
            elif kind == "fanout":
                # Atomic N-way broadcast inside a composite MODULE
                # (backlog 103). Uses the same API as application-
                # level fan-out; the composite's sub-components are
                # already registered, so _fanout can install the
                # source + per-receiver channels.
                self._fanout(
                    binding["sender"], binding["sender_port"],
                    binding["receivers"],
                    owner=component,
                )
            elif kind == "fanin":
                # Atomic per-sender merge inside a composite MODULE
                # (backlog 103).
                self._fanin(
                    binding["senders"],
                    binding["receiver"], binding["receiver_port"],
                    owner=component,
                )
            elif kind == "fanout_buffer_append":
                # Buffered N-way broadcast (backlog 074.1 + 103).
                # Source is a port on the publisher; buffers are the
                # per-subscriber Seq buffers listed by name. Each
                # buffer was already registered by a preceding
                # `buffer` binding.
                source_comp = _resolve_endpoint(
                    component, binding["source"],
                )
                buffers = [
                    component._buffers_by_name[n]
                    for n in binding["buffers"]
                ]
                synth = FanOutBufferAppend(
                    binding["action"],
                    source_comp, binding["source"][1],
                    buffers,
                )
                synth.component = component
                self._synth_actions.append(synth)
            else:
                raise ValueError(
                    f"_internal_bindings: unknown kind {kind!r}"
                )

    def _channel(
        self,
        comp_a: Component,
        port_a: str,
        comp_b: Component,
        port_b: str,
    ) -> Channel:
        """Point-to-point binding. Accepts the two endpoints in
        either order; resolves sender/receiver from each component's
        declared `_in_ports` / `_out_ports`.

        If either side is a composite port (present in that
        component's `_forwards` table), the binding is redirected
        to the forwarded (sub_component, sub_port) before resolving
        direction. Forwards chain recursively -- a two-layer
        composite's EXT_IN -> mid.MID_IN -> leaf.IN all lands on
        leaf.IN.
        """
        comp_a, port_a = self._resolve_forward(comp_a, port_a)
        comp_b, port_b = self._resolve_forward(comp_b, port_b)
        sender, out_port, receiver, in_port = self._resolve_direction(
            comp_a, port_a, comp_b, port_b,
        )
        name = (
            f"{sender._alias}.{out_port}->"
            f"{receiver._alias}.{in_port}"
        )
        ch = Channel(name=name)
        sender._port_channels[out_port] = ch
        receiver._port_channels[in_port] = ch
        self._channels.append(ch)
        return ch

    @staticmethod
    def _forwards_entry(entry) -> tuple[tuple["Component", str], ...]:
        """Normalize a `_forwards[port]` value to a tuple of
        `(Component, str)` endpoints.

        Accepts two shapes:
          - Bare `(comp, port_str)` pair (legacy, used by the
            hand-written composites in design/python-target/ and
            by pre-115 generated code).
          - Tuple of such pairs, emitted by the codegen post-115.

        Detects the bare-pair shape by checking the second element
        is a string; otherwise iterates.
        """
        if (
            isinstance(entry, tuple)
            and len(entry) == 2
            and isinstance(entry[1], str)
        ):
            return (entry,)
        return tuple(entry)

    @staticmethod
    def _resolve_forward_all(
        comp: "Component", port: str,
    ) -> tuple[tuple["Component", str], ...]:
        """Walk a composite's `_forwards` table to the set of leaf
        `(Component, port)` endpoints. One external port may forward
        to multiple sub-components that share a source (typical for
        observe ports, backlog 115). Visited-set check catches
        malformed cycles. BFS over the forwards tree; returns at
        least one endpoint.
        """
        results: list[tuple["Component", str]] = []
        visited: set[tuple[int, str]] = set()
        queue: list[tuple["Component", str]] = [(comp, port)]
        while queue:
            c, p = queue.pop(0)
            forwards = getattr(c, "_forwards", None)
            if not forwards or p not in forwards:
                results.append((c, p))
                continue
            key = (id(c), p)
            if key in visited:
                raise ValueError(
                    f"_forwards cycle detected at "
                    f"{getattr(c, '_alias', '?')}.{p}"
                )
            visited.add(key)
            for endpoint in Application._forwards_entry(forwards[p]):
                queue.append(endpoint)
        return tuple(results)

    @staticmethod
    def _resolve_forward(
        comp: "Component", port: str,
    ) -> tuple["Component", str]:
        """Single-endpoint forward resolution. Wraps
        `_resolve_forward_all` and asserts exactly one leaf target.

        Channel / fan binding call sites expect a single-target
        forward -- an external in/out port forwarding to two
        sub-components is a fan, which is bound separately. This
        helper keeps those call sites simple and surfaces the
        forbidden-shape case as an explicit error.
        """
        endpoints = Application._resolve_forward_all(comp, port)
        if len(endpoints) != 1:
            raise ValueError(
                f"_forwards[{getattr(comp, '_alias', '?')}.{port}] "
                f"resolves to {len(endpoints)} endpoints; "
                f"channel / fan call sites require exactly one. "
                f"Only observe-port forwards allow N>1."
            )
        return endpoints[0]

    @staticmethod
    def _resolve_direction(
        comp_a: Component, port_a: str,
        comp_b: Component, port_b: str,
    ) -> tuple[Component, str, Component, str]:
        """Figure out which (comp, port) is the sender and which is
        the receiver. Uses the components' class-level port
        declarations. Raises if the two ports aren't one-in /
        one-out."""
        a_is_out = port_a in comp_a._out_ports
        a_is_in = port_a in comp_a._in_ports
        b_is_out = port_b in comp_b._out_ports
        b_is_in = port_b in comp_b._in_ports
        if a_is_out and b_is_in:
            return comp_a, port_a, comp_b, port_b
        if b_is_out and a_is_in:
            return comp_b, port_b, comp_a, port_a
        raise ValueError(
            f"_channel: cannot resolve direction for "
            f"{comp_a._alias}.{port_a} <-> {comp_b._alias}.{port_b} "
            f"(neither side is a clean out/in pair)"
        )

    def _observe(
        self,
        observer: Component,
        port_name: str,
        target: Component,
    ) -> None:
        """Bind an observe port to the component being observed.
        Guards on every observer read `target.state` directly.

        If `observer.port_name` is a forwarded composite port, the
        bind lands on every internal sub-component that shares the
        port (backlog 115). A composite whose CoinCup binds WATCH_GM
        to both inner coins resolves to two leaf endpoints; each
        coin gets its own `_observed['WATCH_GM']` entry pointing at
        the same target. Single-target observe forwards continue to
        work -- the tuple-of-endpoints shape collapses to length 1.
        The target side never forwards (we observe a concrete
        component's state, not a composite).
        """
        endpoints = self._resolve_forward_all(observer, port_name)
        for endpoint_comp, endpoint_port in endpoints:
            if endpoint_port not in endpoint_comp._observe_ports:
                raise ValueError(
                    f"{endpoint_comp._alias}.{endpoint_port} "
                    f"is not an observe port"
                )
            endpoint_comp._observed[endpoint_port] = target

    def _fanout(
        self,
        sender: Component,
        out_port: str,
        receivers: list[tuple[Component, str]],
        owner: "Component | None" = None,
    ) -> None:
        """Broadcast: one sender, N receivers. Sender has one source
        channel; each receiver has its own. A synthesized `FanOut`
        action copies source -> all targets atomically when enabled.

        Endpoints may be composite ports; `_resolve_forward` chains
        through to the real leaf sub-component + port before the
        source/target channels are created.

        `owner` tags the synthesized action with its owning composite
        so a component-level `on_<action>` hook fires on the composite
        subclass in `_commit_synth`. APPLICATION-mode callers leave
        `owner=None` (the fan belongs to the Application itself).
        """
        sender, out_port = self._resolve_forward(sender, out_port)
        self._require_out_port(sender, out_port)
        source = Channel(name=f"{sender._alias}.{out_port}->(fanout)")
        sender._port_channels[out_port] = source
        self._channels.append(source)

        targets: list[Channel] = []
        for receiver, in_port in receivers:
            receiver, in_port = self._resolve_forward(receiver, in_port)
            self._require_in_port(receiver, in_port)
            ch_name = (
                f"{sender._alias}.{out_port}->"
                f"{receiver._alias}.{in_port}"
            )
            ch = Channel(name=ch_name)
            receiver._port_channels[in_port] = ch
            self._channels.append(ch)
            targets.append(ch)

        action_name = f"{sender._alias}.{out_port}_fanout"
        fa = FanOut(action_name, source, targets)
        if owner is not None:
            fa.component = owner
        self._synth_actions.append(fa)

    def _fan(
        self,
        endpoints: list[tuple[Component, str]],
        owner: "Component | None" = None,
    ) -> None:
        """Direction-agnostic fan binding. Given N endpoints, look up
        each port's direction on its component's class attrs, group
        by direction, and dispatch to `_fanout` or `_fanin`:

          1 out + N>=2 ins  -> fan-out (out is the publisher)
          1 in  + N>=2 outs -> fan-in  (in is the receiver)

        Composites don't know at codegen time which side is the 1 vs
        the N (the IR has a shared channel variable and 3+ endpoint
        with_mappings, but no direction metadata). The runtime
        resolves it at bind time via class attrs.

        `owner` is passed through to `_fanout` / `_fanin` so the
        synthesized fan action gets tagged with its owning composite
        for component-level hook dispatch.
        """
        ins: list[tuple[Component, str]] = []
        outs: list[tuple[Component, str]] = []
        for comp, port in endpoints:
            comp_, port_ = self._resolve_forward(comp, port)
            if port_ in comp_._in_ports:
                ins.append((comp_, port_))
            elif port_ in comp_._out_ports:
                outs.append((comp_, port_))
            else:
                raise ValueError(
                    f"_fan: {comp_._alias}.{port_} is neither in nor out"
                )
        if len(outs) == 1 and len(ins) >= 2:
            sender, out_port = outs[0]
            self._fanout(sender, out_port, ins, owner=owner)
        elif len(ins) == 1 and len(outs) >= 2:
            receiver, in_port = ins[0]
            self._fanin(outs, receiver, in_port, owner=owner)
        else:
            raise ValueError(
                f"_fan: can't dispatch {len(outs)} senders + "
                f"{len(ins)} receivers"
            )

    def _fanin(
        self,
        senders: list[tuple[Component, str]],
        receiver: Component,
        in_port: str,
        owner: "Component | None" = None,
    ) -> None:
        """Merge: N senders, one receiver. Receiver has one shared
        inbound channel; each sender has its own source. A
        `FanInMerge` action per sender picks that source into the
        shared inbound.

        Endpoints may be composite ports; `_resolve_forward` chains
        through to the real leaf sub-component + port.

        `owner` tags each synthesized merge action with its owning
        composite so a component-level `on_<action>` hook fires on
        the composite subclass. APPLICATION-mode callers leave
        `owner=None` (the merges belong to the Application itself).
        """
        receiver, in_port = self._resolve_forward(receiver, in_port)
        self._require_in_port(receiver, in_port)
        dest = Channel(name=f"(fanin)->{receiver._alias}.{in_port}")
        receiver._port_channels[in_port] = dest
        self._channels.append(dest)

        for sender, out_port in senders:
            sender, out_port = self._resolve_forward(sender, out_port)
            self._require_out_port(sender, out_port)
            src_name = (
                f"{sender._alias}.{out_port}->"
                f"{receiver._alias}.{in_port}"
            )
            source = Channel(name=src_name)
            sender._port_channels[out_port] = source
            self._channels.append(source)
            merge_name = f"{sender._alias}.{out_port}_fanin_merge"
            fim = FanInMerge(merge_name, source, dest)
            if owner is not None:
                fim.component = owner
            self._synth_actions.append(fim)

    def _fanout_buffered(
        self,
        sender: Component,
        out_port: str,
        receivers: list[tuple[Component, str]],
        depth: int,
        append_action: str,
        drain_actions: list[str],
        buffer_names: list[str],
        owner: "Component | None" = None,
    ) -> None:
        """Buffered N-way broadcast (backlog 074.1 + 077). Allocates
        the publisher's distribution channel, one per-receiver
        target channel, and one Seq buffer per receiver. Synthesizes
        one `FanOutBufferAppend` (atomic N-way enqueue: source ->
        every buffer) plus one `BufferDequeue` per receiver (pops
        its buffer head into the receiver's input channel).

        Same shape supports single-link bufferDepth (`receivers`
        length 1): the single buffer's enqueue drains into the
        receiver's port.

        `owner` tags each synthesized action with its optional
        owning composite so component-level hooks fire there too.
        APPLICATION-mode callers leave `owner=None` -- the synth
        actions belong to the Application itself.
        """
        assert len(receivers) == len(drain_actions) == len(buffer_names), (
            "receivers / drain_actions / buffer_names must align"
        )
        sender, out_port = self._resolve_forward(sender, out_port)
        self._require_out_port(sender, out_port)
        source = Channel(name=f"{sender._alias}.{out_port}")
        sender._port_channels[out_port] = source
        self._channels.append(source)

        buffers: list[Buffer] = []
        resolved_receivers: list[tuple[Component, str]] = []
        for (recv, in_port), buf_name in zip(receivers, buffer_names):
            recv, in_port = self._resolve_forward(recv, in_port)
            self._require_in_port(recv, in_port)
            ch = Channel(
                name=f"{sender._alias}.{out_port}->{recv._alias}.{in_port}"
            )
            recv._port_channels[in_port] = ch
            self._channels.append(ch)
            buf = Buffer(name=buf_name, depth=depth)
            self._buffers.append(buf)
            buffers.append(buf)
            resolved_receivers.append((recv, in_port))

        append = FanOutBufferAppend(
            append_action, sender, out_port, buffers,
        )
        if owner is not None:
            append.component = owner
        self._synth_actions.append(append)

        for (recv, in_port), buf, drain_name in zip(
            resolved_receivers, buffers, drain_actions,
        ):
            drain = BufferDequeue(drain_name, buf, recv, in_port)
            if owner is not None:
                drain.component = owner
            self._synth_actions.append(drain)

    def _register_invariant(
        self,
        inv_id: str,
        predicate_fn: Callable[[Application], bool],
    ) -> None:
        self._invariants.append((inv_id, predicate_fn))

    @staticmethod
    def _require_out_port(comp: Component, port: str) -> None:
        if port not in comp._out_ports:
            raise ValueError(f"{comp._alias}.{port} is not an out-port")

    @staticmethod
    def _require_in_port(comp: Component, port: str) -> None:
        if port not in comp._in_ports:
            raise ValueError(f"{comp._alias}.{port} is not an in-port")

    # ----- Enabled-set enumeration --------------------------------

    def _enabled(self) -> list[tuple[str, Component | None, Transition | SynthAction]]:
        """Every action ready to fire right now. Component transitions
        and synthesized actions walked uniformly. The scheduler picks
        from this list; fire() validates against it."""
        out: list[tuple[str, Component | None, Transition | SynthAction]] = []
        for alias, comp in self._components.items():
            for t in comp._transitions:
                if comp.state != t.from_state:
                    continue
                if not self._transition_enabled(comp, t):
                    continue
                out.append((f"{alias}.{t.name}", comp, t))
        for sa in self._synth_actions:
            if sa.is_enabled():
                out.append((sa.name, None, sa))
        return out

    def _transition_enabled(self, comp: Component, t: Transition) -> bool:
        """Guard + per-port channel preconditions. Returns True iff
        firing this transition right now would succeed."""
        if t.guard_fn is not None and not self._safe_guard(comp, t.guard_fn):
            return False
        if t.recv_port is not None and not self._channel_has_inflight(
            comp, t.recv_port, t.recv_tag
        ):
            return False
        if t.send_port is not None and not self._channel_is_clear(
            comp, t.send_port
        ):
            return False
        if t.raise_port is not None and not self._channel_is_clear(
            comp, t.raise_port
        ):
            return False
        return True

    @staticmethod
    def _safe_guard(comp: Component, fn: Callable[[Any], bool]) -> bool:
        """Evaluate a guard; swallow exceptions as "not enabled" so
        a partially-bound component never poisons enumeration."""
        try:
            return bool(fn(comp))
        except Exception:
            return False

    @staticmethod
    def _channel_has_inflight(comp: Component, port: str, tag: str | None) -> bool:
        """Receive guard: channel must be InFlight, and either the
        transition requires a specific tag (must match exactly) or
        it's a wildcard receive (recv_tag=None, matches any tag).

        Backlog 088: untagged receive on a typed channel is a
        wildcard -- TLA+'s `channel = Ch_InFlight` guard is
        satisfied regardless of the tag value stored in the
        channel. Without wildcard semantics, an untagged module
        composed into a typed parent deadlocks in Python where
        TLC would progress."""
        ch = comp._port_channels.get(port)
        if ch is None:
            return False
        if ch.state != "InFlight":
            return False
        if tag is None:
            return True
        return ch.tag == tag

    @staticmethod
    def _channel_is_clear(comp: Component, port: str) -> bool:
        ch = comp._port_channels.get(port)
        if ch is None:
            return False
        return ch.state in ("NotSent", "Delivered")

    # ----- Fire (explicit) / step (scheduler) ---------------------

    def fire(self, qualified_name: str) -> TransitionEvent:
        """Force a named action. Raises DisabledActionError if not
        enabled. Same commit path as `step()`."""
        sa = self._find_synth(qualified_name)
        if sa is not None:
            if not sa.is_enabled():
                raise DisabledActionError(
                    qualified_name, "-", "synth guard not satisfied"
                )
            return self._commit_synth(sa)
        alias, comp, t = self._resolve_component_action(qualified_name)
        if comp.state != t.from_state:
            raise DisabledActionError(
                qualified_name, comp.state,
                f"requires from_state={t.from_state!r}",
            )
        if not self._transition_enabled(comp, t):
            raise DisabledActionError(
                qualified_name, comp.state,
                "guard or channel precondition not satisfied",
            )
        return self._commit(alias, comp, t)

    def step(self) -> TransitionEvent | None:
        """Scheduler pick. Returns the event that fired, or None if
        nothing was enabled."""
        enabled = self._enabled()
        if not enabled:
            self._call_hook("on_step", None)
            return None
        _, comp, thing = self._rng.choice(enabled)
        if isinstance(thing, SynthAction):
            event = self._commit_synth(thing)
        else:
            event = self._commit(comp._alias, comp, thing)
        self._call_hook("on_step", event)
        return event

    def _find_synth(self, name: str) -> SynthAction | None:
        for sa in self._synth_actions:
            if sa.name == name:
                return sa
        return None

    def _resolve_component_action(
        self, qualified_name: str,
    ) -> tuple[str, Component, Transition]:
        # Composite components register with compound aliases like
        # "O.Mid.Leaf". We rpartition on the LAST dot so the alias
        # stays intact and the trailing bit is the transition name.
        # Transition names never contain dots (convention).
        alias, _, action = qualified_name.rpartition(".")
        comp = self._components.get(alias)
        if comp is None:
            raise DisabledActionError(
                qualified_name, "?",
                f"no component registered with alias {alias!r}",
            )
        for t in comp._transitions:
            if t.name == action:
                return alias, comp, t
        raise DisabledActionError(
            qualified_name, comp.state,
            f"component has no transition named {action!r}",
        )

    # ----- Atomic commit: apply -> hooks -> invariants ------------
    #
    # Per transitions.md: all mutations happen inside `_apply`
    # before any hook runs. Hooks see the post-state.

    def _commit(
        self, alias: str, comp: Component, t: Transition,
    ) -> TransitionEvent:
        event = self._apply(alias, comp, t)
        self._call_transition_hooks(alias, comp, event)
        self._evaluate_invariants()
        return event

    def _apply(
        self, alias: str, comp: Component, t: Transition,
    ) -> TransitionEvent:
        """Commit every mutation of this transition. Component state,
        channels, counter, effect_fn -- all before any hook sees a
        thing. Returns the event describing what just happened."""
        from_state = comp.state
        tag: str | None = None
        # MessageSet enforcement: if the component declares a
        # non-empty _message_set (mirroring TLA+'s tagConstants +
        # `\\in MessageSet` guards), any tagged send / raise must
        # use a value from that set. Untagged (None) always OK --
        # matches TLA+'s Ch_InFlight untagged carrier semantics.
        if t.send_port is not None and t.send_tag is not None \
                and comp._message_set and t.send_tag not in comp._message_set:
            raise MessageSetViolation(
                alias, t.send_port, t.send_tag, comp._message_set,
            )
        if t.raise_port is not None and t.raise_tag is not None \
                and comp._message_set and t.raise_tag not in comp._message_set:
            raise MessageSetViolation(
                alias, t.raise_port, t.raise_tag, comp._message_set,
            )
        comp.state = t.to_state
        if t.recv_port is not None:
            ch = comp._port_channels[t.recv_port]
            ch.state = "Delivered"
            tag = ch.tag
            # MODULE tag-forwarding capture (backlog 119). Mirrors
            # TLA+'s `_msgInFlight' = chan` on receives whose host
            # StructuredAction has forward_capture set. The captured
            # tag is what a subsequent PORT_FORWARD send reads.
            if t.forward_capture:
                comp._msg_in_flight = ch.tag
        if t.send_port is not None:
            ch = comp._port_channels[t.send_port]
            # MODULE tag-forwarding send (backlog 119). Mirrors TLA+'s
            # `chan' = _msgInFlight`: instead of setting the outgoing
            # tag to send_tag (which is None for a tagless forwarding
            # triple), use the component's captured in-flight tag.
            if t.forward_send:
                ch.tag = comp._msg_in_flight
            else:
                ch.tag = t.send_tag
            ch.state = "InFlight"
            if tag is None:
                tag = ch.tag
        if t.raise_port is not None:
            ch = comp._port_channels[t.raise_port]
            ch.tag = t.raise_tag
            ch.state = "InFlight"
        if t.counter_increment is not None:
            comp._counters[t.counter_increment] += 1
        for var_name, value_fn in t.assigns:
            setattr(comp, var_name, value_fn(comp))
        if t.effect_fn is not None:
            t.effect_fn(comp)
        qname = f"{alias}.{t.name}"
        self._last_action = qname
        return TransitionEvent(
            qualified_name=qname,
            action_name=t.name,
            component_alias=alias,
            from_state=from_state,
            to_state=t.to_state,
            tag=tag,
        )

    def _commit_synth(self, sa: SynthAction) -> TransitionEvent:
        """Atomic commit for a synthesized action. Fires two
        app-level hooks: the per-action name (with dots normalized
        to underscores so compound-alias fan actions -- e.g.
        `c.P.OUT_fanout` -- have valid Python identifiers that
        `getattr` can resolve) and the catch-all `on_fire`. The
        event's `action_name` and `qualified_name` retain the raw
        `.`-separated form so trace logs read the original
        identifier.

        Synth actions belonging to a composite (buffer / fan
        bindings replayed from `_internal_bindings`) optionally
        carry a `component` attribute pointing at the owning
        composite; if present, a component-level `on_<action>`
        hook on the composite subclass also fires -- matches the
        real-transition hook dispatch.
        """
        sa.apply()
        self._last_action = sa.name
        event = TransitionEvent(
            qualified_name=sa.name,
            action_name=sa.name,
            component_alias="",
            from_state="",
            to_state="",
            tag=None,
        )
        hook_id = sa.name.replace(".", "_")
        self._call_hook(f"on_{hook_id}", event)
        self._call_hook("on_fire", event)
        owner = getattr(sa, "component", None)
        if owner is not None:
            self._call_hook_on(owner, f"on_{hook_id}", event)
        self._evaluate_invariants()
        return event

    # ----- Hook dispatch ------------------------------------------
    #
    # Dispatch by method name via getattr. A hook that isn't defined
    # is a no-op. The list of hooks fired per transition is explicit
    # in `_call_transition_hooks` so a reviewer sees it whole.

    def _call_transition_hooks(
        self, alias: str, comp: Component, event: TransitionEvent,
    ) -> None:
        """Fire every hook that applies to this transition, in a
        fixed order: exit, action, enter, catch-all. App-level hooks
        use alias-prefixed names; component-level hooks use bare
        names (no prefix). Users override whichever fits.

        Compound aliases (e.g. `O.Mid.Leaf` for components nested
        in composites) get their dots replaced with underscores in
        hook names so they're valid Python identifiers. User writes
        `def on_O_Mid_Leaf_Leaf_Handle(self, event)`.
        """
        alias_id = alias.replace(".", "_")
        app_hooks = [
            f"on_{alias_id}_exit_{event.from_state}",
            f"on_{alias_id}_{event.action_name}",
            f"on_{alias_id}_enter_{event.to_state}",
            "on_fire",
        ]
        comp_hooks = [
            f"on_exit_{event.from_state}",
            f"on_{event.action_name}",
            f"on_enter_{event.to_state}",
        ]
        for name in app_hooks:
            self._call_hook(name, event)
        for name in comp_hooks:
            self._call_hook_on(comp, name, event)

    def _call_hook(self, name: str, *args: Any) -> None:
        """Invoke `self.<name>(*args)` if defined; otherwise no-op."""
        method = getattr(self, name, None)
        if callable(method):
            method(*args)

    @staticmethod
    def _call_hook_on(target: Any, name: str, *args: Any) -> None:
        """Invoke `target.<name>(*args)` if defined; otherwise no-op."""
        method = getattr(target, name, None)
        if callable(method):
            method(*args)

    def on_invariant_violated(self, exc: InvariantViolation) -> None:
        """Default: raise. Subclasses override to log, alert, or
        continue (the explicit non-default behavior)."""
        raise exc

    # ----- Invariant evaluation -----------------------------------

    def _evaluate_invariants(self) -> None:
        """Per invariants.md: every registered predicate evaluates
        after every state change. Failures flow through
        `on_invariant_violated` -- default raises."""
        for inv_id, predicate in self._invariants:
            try:
                ok = predicate(self)
            except Exception as e:
                self.on_invariant_violated(InvariantViolation(
                    inv_id, f"evaluation raised {e!r}", self._last_action,
                ))
                continue
            if not ok:
                self.on_invariant_violated(InvariantViolation(
                    inv_id, self._state_summary(), self._last_action,
                ))

    def _state_summary(self) -> str:
        return ", ".join(
            f"{alias}={comp.state}"
            for alias, comp in self._components.items()
        )

    # ----- Snapshot / restore / replay ----------------------------

    def state_snapshot(self) -> dict[str, Any]:
        """Flat dict projection of spec-level state. Keyed by
        `<Alias>.state`, `<Alias>.<counter>`, the channel's own
        `name` attribute, and a buffer's `name` attribute (for
        buffered ports). Used by `replay()` to compare against a
        recorded trace."""
        snap: dict[str, Any] = {}
        for alias, comp in self._components.items():
            snap[f"{alias}.state"] = comp.state
            for name, val in comp._counters.items():
                snap[f"{alias}.{name}"] = val
        for ch in self._channels:
            snap[ch.name] = (ch.state, ch.tag)
        for buf in self._buffers:
            snap[buf.name] = tuple(buf.items)
        return snap

    def replay(
        self,
        trace: list[tuple[str | None, dict[str, Any]]],
    ) -> None:
        """Drive a recorded trace through the app. Each entry is
        `(action_name, expected_state_after)`. action=None means
        "check the current state without firing anything" -- the
        conventional first entry for the initial state. Raises
        ReplayDivergence at the first mismatched variable."""
        for step_idx, (action, expected) in enumerate(trace):
            if action is not None:
                self.fire(action)
            actual = self.state_snapshot()
            diffs = {
                key: (exp, actual.get(key))
                for key, exp in expected.items()
                if actual.get(key) != exp
            }
            if diffs:
                raise ReplayDivergence(step_idx, action, diffs)

    def snapshot(self) -> dict:
        """Capture full runtime state (components + channels +
        buffers + RNG) for later `restore()`. Use for counterfactual
        branching."""
        return {
            "components": {
                alias: (comp.state, dict(comp._counters), comp._msg_in_flight)
                for alias, comp in self._components.items()
            },
            "channels": [ch.snapshot() for ch in self._channels],
            "buffers": [buf.snapshot() for buf in self._buffers],
            "rng_state": self._rng.getstate(),
            "last_action": self._last_action,
        }

    def restore(self, snap: dict) -> None:
        for alias, entry in snap["components"].items():
            comp = self._components[alias]
            # Back-compat with pre-119 snapshots (2-tuple).
            if len(entry) == 2:
                state, counters = entry
                msg_in_flight = None
            else:
                state, counters, msg_in_flight = entry
            comp.state = state
            comp._counters = dict(counters)
            comp._msg_in_flight = msg_in_flight
        for ch, ch_snap in zip(self._channels, snap["channels"]):
            ch.restore(ch_snap)
        for buf, buf_snap in zip(self._buffers, snap.get("buffers", ())):
            buf.restore(buf_snap)
        self._rng.setstate(snap["rng_state"])
        self._last_action = snap["last_action"]


# ---------------------------------------------------------------------------
# Binding-replay helpers
# ---------------------------------------------------------------------------


def _resolve_endpoint(
    composite: Component, endpoint: tuple[str, str],
) -> Component:
    """Map a buffer-binding endpoint `(alias, port)` to the Component
    holding that port. Alias `""` means the composite itself;
    otherwise it's one of the composite's sub-components. The port
    name goes back to the caller untouched -- the runtime looks up
    the Channel on `_port_channels` lazily at fire time.
    """
    alias, _port = endpoint
    if alias == "":
        return composite
    return composite._sub_components[alias]
