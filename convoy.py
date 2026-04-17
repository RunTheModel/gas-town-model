"""Console demo of the convoy-lands simulator. No Streamlit required.

Usage: python convoy.py
"""
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "bin"))

from ConvoyLands import ConvoyLands

def pretty(s):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', s).replace('M R', 'MR')

NAMES = {
    "May": "Mayor", "Con": "Convoy", "Fed": "Feeder",
    "Ref": "Refinery", "Lnd": "Landing",
    "Iss1": "Issue 1", "Iss2": "Issue 2",
    "Pol1": "Polecat 1", "Pol2": "Polecat 2",
    "Mr1": "Merge Request 1", "Mr2": "Merge Request 2",
    "Wt1": "Worktree 1", "Wt2": "Worktree 2",
    "Hk1": "PreCompact Hook 1", "Hk2": "PreCompact Hook 2",
}

sim = ConvoyLands(seed=42)
step = 0

while True:
    transitions = [(a, t) for a, t in sim.enabled_transitions()
                   if t.from_state != t.to_state]

    if not transitions:
        print("\nNo enabled transitions. System quiesced.")
        break

    print(f"\n--- Step {step} ---")
    print("State:")
    for alias, comp in sim._components.items():
        print(f"  {NAMES.get(alias, alias):25s} {pretty(comp.state)}")

    print("\nAvailable transitions:")
    for i, (alias, t) in enumerate(transitions):
        print(f"  [{i}] {NAMES.get(alias, alias)}: {pretty(t.from_state)} -> {pretty(t.to_state)}")

    choice = input("\nPick a transition (number), 'r' for random, or 'q' to quit: ").strip()

    if choice == 'q':
        break
    elif choice == 'r':
        sim.step()
    else:
        try:
            idx = int(choice)
            alias, t = transitions[idx]
            sim._components[alias].fire(t)
        except (ValueError, IndexError):
            print("Invalid choice.")
            continue

    step += 1
    try:
        sim.check_invariants()
    except Exception as e:
        print(f"\n*** INVARIANT VIOLATION: {e} ***")
        break

print(f"\nFinal state after {step} steps:")
for alias, comp in sim._components.items():
    print(f"  {NAMES.get(alias, alias):25s} {pretty(comp.state)}")
