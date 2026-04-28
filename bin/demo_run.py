"""Demo runner: bound steps, report final state and invariant status.

Usage: python <Spec>.py --run demo_run.py --seed N

Runs the bound `app` for up to MAX_STEPS, reports final bead/sling states.
The runtime raises InvariantViolation on any failure; this script catches
and reports cleanly so the bug-vs-fix contrast is visible per-seed.
"""
from kinner_runtime import InvariantViolation

MAX_STEPS = 5000

try:
    for i in range(MAX_STEPS):
        if app.step() is None:
            print(f"terminated at step {i}")
            break
    else:
        print(f"ran {MAX_STEPS} steps (terminal self-loops may continue)")
    print("INVARIANT: HookedSingleton held throughout the run")
except InvariantViolation as e:
    print(f"INVARIANT VIOLATED: {e}")

print("Final bead states:")
for alias in sorted(app._components):
    if alias.startswith("Bead"):
        print(f"  {alias}: {app._components[alias].state}")
