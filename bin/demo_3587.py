"""Demo runner for gate-3587 specs. Reports Polecat's final state.

Usage: python <Spec>.py --run demo_3587.py --seed N

In the bug spec, ~half of seeds will have Deacon crash before sending wake;
those traces leave Polecat=Parked. In the fix spec, every seed reaches
Polecat=Working because PrimeRecovery self-heals when Deacon crashes.
"""
MAX_STEPS = 2000

for i in range(MAX_STEPS):
    if app.step() is None:
        print(f"terminated at step {i}")
        break
else:
    print(f"ran {MAX_STEPS} steps (terminal self-loops may continue)")

pol = app._components.get("Pol")
gt = app._components.get("Gt")
dec = app._components.get("Dec")
pr = app._components.get("Pr")

print(f"Final state:")
print(f"  Pol  = {pol.state if pol else '?'}")
print(f"  Gt   = {gt.state if gt else '?'}")
print(f"  Dec  = {dec.state if dec else '?'}")
if pr is not None:
    print(f"  Pr   = {pr.state}")

if pol and pol.state == "Working":
    print("OUTCOME: polecat resumed (correct)")
elif pol and pol.state == "Parked":
    print("OUTCOME: polecat STUCK in Parked (bug demonstrated)" if dec and dec.state == "Crashed"
          else "OUTCOME: polecat still Parked (Deacon hasn't completed)")
else:
    print(f"OUTCOME: unexpected state {pol.state if pol else '?'}")
