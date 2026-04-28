"""Run many seeds, tally violation rate.

Usage: python <Spec>.py --run demo_seeds.py [--seeds N]

Defaults to 200 seeds, 1000 steps each. Catches InvariantViolation per
seed so the run continues. Reports the violation rate at the end.
"""
import sys
from kinner_runtime import InvariantViolation

# Parse N from argv if provided as a positional arg after demo_seeds.py
N_SEEDS = 200
MAX_STEPS = 10000

# `app` is bound by the --run mechanism but only carries seed=0.
# We need to construct fresh apps with different seeds. Get the class
# from the bound app:
SpecClass = type(app)

violations = 0
violation_states = []
clean = 0
trapped = 0  # ran MAX_STEPS without finding terminal

for seed in range(N_SEEDS):
    a = SpecClass(seed=seed)
    try:
        for i in range(MAX_STEPS):
            if a.step() is None:
                clean += 1
                break
        else:
            trapped += 1
    except InvariantViolation as e:
        violations += 1
        violation_states.append((seed, str(e).split(":")[0]))

print(f"seeds: {N_SEEDS}, max_steps_per_seed: {MAX_STEPS}")
print(f"  violations:   {violations} ({100*violations/N_SEEDS:.1f}%)")
print(f"  clean (terminated naturally):  {clean}")
print(f"  trapped (hit step limit):      {trapped}")
if violations:
    print(f"  first violations at seeds: {[s for s,_ in violation_states[:10]]}")
