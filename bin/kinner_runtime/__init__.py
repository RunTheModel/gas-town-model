"""
kinner_runtime -- Python runtime for Kinner-generated simulators.

Companion library for the earhart `--target python` backend. Generated
code imports from this module. Hand-written; not emitted.

Kept deliberately small (see backlog/066). The value is in the generated
code, not here. No async, no threading, no persistence. Pure synchronous
state-machine simulation.

Public surface:

    Channel              -- three-state message holder (NotSent/InFlight/Delivered)
    Component            -- base class for generated actor/module classes
    Application          -- base class for generated project/composite classes
    Transition           -- declarative tuple describing one state transition
    InvariantViolation   -- raised when a named invariant evaluates False
    UnboundPortError     -- raised when firing a send on an unbound out-port
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------


class Channel:
    """Three-state message holder shared between a sender and a receiver.

    States are tuple-encoded so peek/equality is trivial:
        ("NotSent", None)
        ("InFlight", tag)
        ("Delivered", None)

    The untyped/default tag is "msg" -- matches the TLA+ emitter's default.
    """

    __slots__ = ("state",)

    def __init__(self) -> None:
        self.state: tuple[str, str | None] = ("NotSent", None)

    def send(self, tag: str = "msg") -> None:
        self.state = ("InFlight", tag)

    def consume(self) -> None:
        self.state = ("Delivered", None)

    def reset(self) -> None:
        self.state = ("NotSent", None)

    def peek(self) -> tuple[str, str | None]:
        return self.state

    def in_flight_with(self, tag: str) -> bool:
        return self.state == ("InFlight", tag)

    def is_clear(self) -> bool:
        """True when a sender can transmit: NotSent or already Delivered."""
        return self.state[0] in ("NotSent", "Delivered")

    def __repr__(self) -> str:
        kind, tag = self.state
        if tag is None:
            return f"Channel({kind})"
        return f"Channel({kind}, tag={tag!r})"


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Transition:
    """One row from an actor's triples list. The emitter produces a list of
    these per Component subclass.

    `kind` is one of "local", "send", "receive".
    `port` is the port name for send/receive transitions; None for local.
    `tag` is the message tag for send (what we transmit) or receive
        (what we pattern-match on). None for local or untagged msg.
    `guard_fn(component) -> bool` evaluates the triple's guard against
        the component's observe-port state + counters. None means always true.
    `effect_fn(component)` runs after state transition; may be None.
        Used for counter increments.
    """

    name: str
    from_state: str
    to_state: str
    kind: str
    port: str | None = None
    tag: str | None = None
    guard_fn: Callable[[Any], bool] | None = None
    effect_fn: Callable[[Any], None] | None = None


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class UnboundPortError(RuntimeError):
    """Raised when a send transition fires on a port that has no bound
    out-channel. Sending to nobody is a wiring mistake, not a silent no-op.
    """


class Component:
    """Base class for every generated library-module class.

    Holds: `state` (string), `_observed` (port name -> Component | None),
    `_channels_in` / `_channels_out` (port name -> Channel | None),
    `_counters` (counter name -> int), and a `transitions` list.

    Every generated subclass overrides:
      - `initial_state: str` -- the state to start in
      - `state_constants: tuple[str, ...]` -- all valid states
      - `_observe_ports: tuple[str, ...]` -- names of observe ports
      - `_in_ports: tuple[str, ...]` -- names of in ports
      - `_out_ports: tuple[str, ...]` -- names of out ports
      - `_counter_defaults: dict[str, int]` -- counter bounds (optional)
      - `_build_transitions(self) -> list[Transition]` -- triples
    """

    initial_state: str = ""
    state_constants: tuple[str, ...] = ()
    _observe_ports: tuple[str, ...] = ()
    _in_ports: tuple[str, ...] = ()
    _out_ports: tuple[str, ...] = ()
    _counter_defaults: dict[str, int] = {}

    def __init__(self) -> None:
        self.state: str = self.initial_state
        self._observed: dict[str, Component | None] = {
            p: None for p in self._observe_ports
        }
        self._channels_in: dict[str, Channel | None] = {
            p: None for p in self._in_ports
        }
        self._channels_out: dict[str, Channel | None] = {
            p: None for p in self._out_ports
        }
        self._counters: dict[str, int] = {
            n: 0 for n in self._counter_defaults
        }
        self.transitions: list[Transition] = self._build_transitions()

    def _build_transitions(self) -> list[Transition]:
        return []

    # ----- Binding helpers (used by Application wiring or by unit tests) ----

    def bind_observe(self, port: str, target: "Component") -> None:
        if port not in self._observed:
            raise ValueError(f"{type(self).__name__} has no observe port {port!r}")
        self._observed[port] = target

    def bind_in(self, port: str, channel: Channel) -> None:
        if port not in self._channels_in:
            raise ValueError(f"{type(self).__name__} has no in port {port!r}")
        self._channels_in[port] = channel

    def bind_out(self, port: str, channel: Channel) -> None:
        if port not in self._channels_out:
            raise ValueError(f"{type(self).__name__} has no out port {port!r}")
        self._channels_out[port] = channel

    # ----- Transition evaluation -------------------------------------------

    def enabled_transitions(self) -> list[Transition]:
        """Every triple whose from_state matches self.state, whose guard is
        True, and whose receive precondition (if any) is met. Unbound
        in-channels make receive transitions unreachable (silently false).
        """
        out: list[Transition] = []
        for t in self.transitions:
            if t.from_state != self.state:
                continue
            if t.kind == "receive":
                ch = self._channels_in.get(t.port) if t.port else None
                if ch is None:
                    continue
                expected = t.tag or "msg"
                if not ch.in_flight_with(expected):
                    continue
            if t.guard_fn is not None:
                try:
                    if not t.guard_fn(self):
                        continue
                except Exception:
                    # Malformed guard should not crash the scheduler --
                    # treat as disabled. The test suite catches broken
                    # guards via negative assertions.
                    continue
            if t.kind == "send":
                ch = self._channels_out.get(t.port) if t.port else None
                if ch is None:
                    # Unbound -- still "enabled" at selection time; fire()
                    # will raise UnboundPortError. This gives a clear error
                    # at step-time rather than silently hiding the send.
                    pass
                elif not ch.is_clear():
                    continue
            out.append(t)
        return out

    def fire(self, t: Transition) -> None:
        """Apply one transition. Must be one returned by enabled_transitions()
        and state must still equal t.from_state.

        Calls optional hook methods on the subclass (backlog/067):
          - on_exit_<state>(t)    before state change
          - on_enter_<state>(t)   after state change
          - on_send_<tag>(t)      after the channel was marked InFlight
          - on_receive_<tag>(t)   after the channel was consumed

        Hooks are looked up with getattr; absent hooks have zero cost.
        Exceptions from hooks propagate to the caller -- the runtime does
        not wrap them.
        """
        prev = self.state
        exit_handler = getattr(self, f"on_exit_{prev}", None)
        if exit_handler is not None:
            exit_handler(t)
        self.state = t.to_state
        if t.kind == "send":
            ch = self._channels_out.get(t.port) if t.port else None
            if ch is None:
                # Restore state so the exception is non-destructive.
                self.state = prev
                raise UnboundPortError(
                    f"{type(self).__name__}.{t.port}: send has no bound channel"
                )
            ch.send(t.tag or "msg")
            if t.tag:
                send_handler = getattr(self, f"on_send_{t.tag}", None)
                if send_handler is not None:
                    send_handler(t)
        elif t.kind == "receive":
            ch = self._channels_in.get(t.port) if t.port else None
            if ch is not None:
                ch.consume()
            if t.tag:
                recv_handler = getattr(self, f"on_receive_{t.tag}", None)
                if recv_handler is not None:
                    recv_handler(t)
        enter_handler = getattr(self, f"on_enter_{t.to_state}", None)
        if enter_handler is not None:
            enter_handler(t)
        if t.effect_fn is not None:
            t.effect_fn(self)

    # ----- Debugging ------------------------------------------------------

    def __repr__(self) -> str:
        return f"{type(self).__name__}(state={self.state!r})"


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Invariant:
    """One application-level safety invariant. `fn(app) -> bool` returns
    True when the invariant holds."""
    id: str
    fn: Callable[[Any], bool]
    description: str = ""


class InvariantViolation(AssertionError):
    """Raised when an invariant evaluates False after a step.

    Attributes:
        invariant_id: the violated invariant's id
        step_number: the step count at which the violation was observed
        trace: list of trace entries leading to the violation
        application: the Application instance, for ad-hoc inspection
    """

    def __init__(
        self,
        invariant_id: str,
        step_number: int,
        trace: list[tuple],
        application: "Application",
    ) -> None:
        self.invariant_id = invariant_id
        self.step_number = step_number
        self.trace = list(trace)
        self.application = application
        super().__init__(self._render())

    def _render(self) -> str:
        lines = [
            f"Invariant {self.invariant_id!r} violated at step {self.step_number}.",
            "Trace:",
        ]
        for entry in self.trace:
            step_n, name, comp, frm, to = entry
            lines.append(f"  [{step_n:>4}] {comp}: {frm} -> {to}  ({name})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class Application:
    """Base class for every generated project/composite-spec class.

    Generated subclass overrides `__init__` to:
      1. Call `super().__init__(seed=seed)`.
      2. Instantiate components (`self.alias = SomeComponent()`).
      3. Wire channels (`self._channels[...] = Channel()`), bind them to
         sender's out-port + receiver's in-port.
      4. Wire observe bindings (`self.obs.bind_observe("PORT", self.target)`).
      5. Register components: `self._register(alias_name, component)`.
      6. Register invariants: `self._invariants.append(Invariant(...))`.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._components: dict[str, Component] = {}
        self._channels: dict[str, Channel] = {}
        self._invariants: list[Invariant] = []
        self.trace: list[tuple[int, str, str, str, str]] = []
        self._step_count: int = 0
        self._rng = random.Random(seed)

    def _register(self, alias: str, component: Component) -> None:
        self._components[alias] = component

    def _bind(self) -> None:
        """Wire channels and observe bindings against current component
        instance references. Generated subclasses override this; the base
        implementation is a no-op so a subclass that replaces components
        in __init__ and calls _rewire() works even without overriding."""

    def _rewire(self) -> None:
        """Re-run channel + observe bindings against current component
        instance references. Call this in a subclass after replacing a
        component (e.g., self.iss1 = MyIssue()).

        Clears every component's observe refs and in/out channels, drops
        the shared channel dict, then re-executes _bind().
        """
        for comp in self._components.values():
            comp._observed = {p: None for p in comp._observe_ports}
            comp._channels_in = {p: None for p in comp._in_ports}
            comp._channels_out = {p: None for p in comp._out_ports}
        self._channels = {}
        self._bind()

    # ----- Enumeration ----------------------------------------------------

    def enabled_transitions(self) -> list[tuple[str, Transition]]:
        """Every (alias, transition) pair currently enabled across the
        whole application. Uniformly random selection over this list is
        the step policy."""
        result: list[tuple[str, Transition]] = []
        for alias, comp in self._components.items():
            for t in comp.enabled_transitions():
                result.append((alias, t))
        return result

    # ----- Step / run -----------------------------------------------------

    def step(self) -> tuple[str, Transition] | None:
        """Pick one enabled transition uniformly at random and fire it.
        Records a trace entry. Returns (alias, transition) or None if no
        transition was enabled (terminal state)."""
        enabled = self.enabled_transitions()
        if not enabled:
            return None
        self._step_count += 1
        alias, t = self._rng.choice(enabled)
        comp = self._components[alias]
        frm = comp.state
        comp.fire(t)
        self.trace.append((self._step_count, t.name, alias, frm, t.to_state))
        return alias, t

    def check_invariants(self) -> None:
        """Evaluate every invariant. Raises InvariantViolation on the
        first failure."""
        for inv in self._invariants:
            try:
                ok = bool(inv.fn(self))
            except Exception as e:
                # A guard-exception on an invariant is itself a failure:
                # the invariant couldn't even evaluate, so treat as violated.
                raise InvariantViolation(
                    inv.id + " (evaluation error: " + str(e) + ")",
                    self._step_count,
                    self.trace,
                    self,
                )
            if not ok:
                raise InvariantViolation(
                    inv.id, self._step_count, self.trace, self
                )

    def run(self, n: int) -> int:
        """Step up to n times, checking invariants between each step.
        Returns the number of steps actually taken (may be < n if the
        simulation reaches a terminal state with no enabled transitions)."""
        for i in range(n):
            if self.step() is None:
                return i
            self.check_invariants()
        return n

    # ----- Introspection --------------------------------------------------

    def state_snapshot(self) -> dict[str, str]:
        """A dict of {alias: current_state} across all components. Useful
        for debugging and for spot-assertions in tests."""
        return {a: c.state for a, c in self._components.items()}

    def __repr__(self) -> str:
        inner = ", ".join(f"{a}={c.state}" for a, c in self._components.items())
        return f"{type(self).__name__}({inner})"
