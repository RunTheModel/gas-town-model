"""Run many seeds for gate-3587, tally outcome."""
N_SEEDS = 200
MAX_STEPS = 2000

SpecClass = type(app)

stuck_in_parked = 0
deacon_crashed_polecat_resumed = 0
deacon_completed_polecat_resumed = 0
other = 0

for seed in range(N_SEEDS):
    a = SpecClass(seed=seed)
    for i in range(MAX_STEPS):
        if a.step() is None:
            break
    pol = a._components["Pol"]
    dec = a._components["Dec"]
    if pol.state == "Parked" and dec.state == "Crashed":
        stuck_in_parked += 1
    elif pol.state == "Working" and dec.state == "Crashed":
        deacon_crashed_polecat_resumed += 1
    elif pol.state == "Working" and dec.state == "Done":
        deacon_completed_polecat_resumed += 1
    else:
        other += 1

print(f"seeds: {N_SEEDS}")
print(f"  stuck in Parked (BUG):                       {stuck_in_parked} ({100*stuck_in_parked/N_SEEDS:.1f}%)")
print(f"  Deacon crashed but Polecat resumed (fix):    {deacon_crashed_polecat_resumed}")
print(f"  Deacon completed normally, Polecat resumed:  {deacon_completed_polecat_resumed}")
print(f"  other:                                       {other}")
