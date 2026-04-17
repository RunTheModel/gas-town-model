import sys
from pathlib import Path

# Add bin/ to the import path so we can find the generated modules
sys.path.insert(0, str(Path(__file__).parent / "bin"))

import streamlit as st
from ConvoyLands import ConvoyLands

st.set_page_config(page_title="Convoy Lands -- Gas Town Simulator", layout="wide")
st.title("Convoy Lands")
st.caption("An interactive simulator of the Gas Town convoy-landing flow. "
           "15 components, 4 safety invariants, generated from a verified Kinner spec. "
           "Click transitions to step through the system. "
           "Grey buttons mean the guard isn't satisfied -- the model won't let you cheat.")

if "sim" not in st.session_state:
    st.session_state.sim = ConvoyLands(seed=42)
    st.session_state.step_count = 0
    st.session_state.violations = []

sim = st.session_state.sim

# Sidebar: controls + branding
with st.sidebar:
    st.header("Controls")
    if st.button("Reset"):
        st.session_state.sim = ConvoyLands(seed=42)
        st.session_state.step_count = 0
        st.session_state.violations = []
        st.rerun()
    st.metric("Steps", st.session_state.step_count)
    if st.session_state.violations:
        st.error(f"{len(st.session_state.violations)} violation(s)")

    st.divider()
    st.markdown("**Sponsored by [runthemodel.dev](https://runthemodel.dev)**")
    st.markdown(
        "[Blog](https://runthemodel.substack.com) | "
        "[GitHub](https://github.com/RunTheModel) | "
        "[Source for this demo](https://github.com/RunTheModel/gas-town-model)"
    )

# Collect enabled transitions, skip self-loops
enabled = [(alias, tr) for alias, tr in sim.enabled_transitions()
           if tr.from_state != tr.to_state]

# Group by component alias
transitions_by_alias = {}
for alias, tr in enabled:
    transitions_by_alias.setdefault(alias, []).append(tr)

# Render actor cards
cols = st.columns(3)
for i, (alias, comp) in enumerate(sim._components.items()):
    with cols[i % 3]:
        st.subheader(alias)
        st.caption(type(comp).__name__)
        st.code(comp.state, language=None)

        for tr in transitions_by_alias.get(alias, []):
            label = f"{tr.from_state} \u2192 {tr.to_state}"
            key = f"{alias}_{tr.name}_{st.session_state.step_count}"
            if st.button(label, key=key, help=tr.name):
                try:
                    comp.fire(tr)
                    st.session_state.step_count += 1
                    try:
                        sim.check_invariants()
                    except Exception as inv:
                        st.session_state.violations.append(str(inv))
                except Exception as e:
                    st.session_state.violations.append(f"\u26a0 {e}")
                st.rerun()

# Show recent trace
if sim.trace:
    st.divider()
    st.subheader("Recent trace")
    for entry in sim.trace[-10:]:
        step, name, component, from_s, to_s = entry
        if from_s != to_s:
            st.text(f"[{step:4d}] {component}: {from_s} \u2192 {to_s}")

# Show violations
if st.session_state.violations:
    st.divider()
    st.subheader("Invariant Violations")
    for v in st.session_state.violations:
        st.error(v)
