import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "bin"))

import streamlit as st
from ConvoyLands import ConvoyLands

st.set_page_config(page_title="Land the Convoy -- Gas Town Simulator sponsored by runthemodel.dev", layout="wide")

# Minimal CSS: just hide the toolbar and make state text pop
st.markdown("""
<style>
    [data-testid="stToolbar"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

NAMES = {
    "May": "Mayor", "Con": "Convoy", "Fed": "Feeder",
    "Ref": "Refinery", "Lnd": "Landing",
    "Iss1": "Issue 1", "Iss2": "Issue 2",
    "Pol1": "Polecat 1", "Pol2": "Polecat 2",
    "Mr1": "Merge Request 1", "Mr2": "Merge Request 2",
    "Wt1": "Worktree 1", "Wt2": "Worktree 2",
    "Hk1": "PreCompact Hook 1", "Hk2": "PreCompact Hook 2",
}

DESCRIPTIONS = {
    "May": "Global coordinator. Launches convoys and decides when to land them.",
    "Con": "A batch of related work items. Lands when all work is integrated.",
    "Fed": "Dispatches work items to polecats. Can send them in any order.",
    "Ref": "The merge queue. Processes merge requests one at a time.",
    "Lnd": "Cleans up worktrees before the convoy can land.",
    "Iss1": "A work item tracked as a bead. Slung by the feeder, worked by a polecat.",
    "Iss2": "A work item tracked as a bead. Slung by the feeder, worked by a polecat.",
    "Pol1": "An AI agent (Claude session) that does the actual work.",
    "Pol2": "An AI agent (Claude session) that does the actual work.",
    "Mr1": "The code branch a polecat produces. Merged by the refinery.",
    "Mr2": "The code branch a polecat produces. Merged by the refinery.",
    "Wt1": "On-disk git worktree. Cleaned up when the convoy lands.",
    "Wt2": "On-disk git worktree. Cleaned up when the convoy lands.",
    "Hk1": "Fires when the AI's context window fills up. May interrupt work.",
    "Hk2": "Fires when the AI's context window fills up. May interrupt work.",
}

DOCS = {
    "May": "https://docs.gastownhall.ai/design/architecture/",
    "Con": "https://docs.gastownhall.ai/design/convoy-lifecycle/",
    "Fed": "https://docs.gastownhall.ai/design/architecture/",
    "Ref": "https://docs.gastownhall.ai/design/architecture/",
    "Lnd": "https://docs.gastownhall.ai/design/convoy-lifecycle/",
    "Iss1": "https://docs.gastownhall.ai/design/architecture/",
    "Iss2": "https://docs.gastownhall.ai/design/architecture/",
    "Pol1": "https://docs.gastownhall.ai/concepts/polecat-lifecycle/",
    "Pol2": "https://docs.gastownhall.ai/concepts/polecat-lifecycle/",
    "Mr1": "https://docs.gastownhall.ai/design/architecture/",
    "Mr2": "https://docs.gastownhall.ai/design/architecture/",
    "Wt1": "https://docs.gastownhall.ai/concepts/polecat-lifecycle/",
    "Wt2": "https://docs.gastownhall.ai/concepts/polecat-lifecycle/",
    "Hk1": "https://docs.gastownhall.ai/concepts/propulsion-principle/",
    "Hk2": "https://docs.gastownhall.ai/concepts/propulsion-principle/",
}

STATE_LABELS = {
    "HandlingHook": "Handling Interrupt",
}

def pretty_state(s):
    if s in STATE_LABELS:
        return STATE_LABELS[s]
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', s).replace('M R', 'MR')

st.title("Land the Convoy")
st.caption("An interactive simulator of the Gas Town convoy-landing flow. "
           "15 components, 4 safety invariants, generated from a verified Kinner spec. "
           "Click transitions to step through the system. "
           "Grey buttons mean the guard isn't satisfied -- the model won't let you cheat.")

if "sim" not in st.session_state:
    st.session_state.sim = ConvoyLands(seed=42)
    st.session_state.step_count = 0
    st.session_state.violations = []

sim = st.session_state.sim

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
    st.markdown("**How this was made**")
    st.markdown(
        "A Kinner model of the Gas Town convoy-landing flow was verified "
        "with TLA+ and then compiled into the Python running this page "
        "using the EARHART compiler. "
        "[View the model source.](https://github.com/RunTheModel/gas-town-model)"
    )
    st.divider()
    st.markdown('<p style="color: #e0e0e0;"><strong>Sponsored by <a href="https://runthemodel.dev" style="color: #e94560;">runthemodel.dev</a></strong></p>', unsafe_allow_html=True)
    st.markdown('<p style="color: #e0e0e0;"><a href="https://runthemodel.substack.com" style="color: #e94560;">Blog</a> | <a href="https://github.com/RunTheModel/gas-town-model" style="color: #e94560;">GitHub</a></p>', unsafe_allow_html=True)

enabled = [(alias, tr) for alias, tr in sim.enabled_transitions()
           if tr.from_state != tr.to_state]

transitions_by_alias = {}
for alias, tr in enabled:
    transitions_by_alias.setdefault(alias, []).append(tr)

cols = st.columns(3)
for i, (alias, comp) in enumerate(sim._components.items()):
    with cols[i % 3]:
        with st.container(border=True):
            doc_url = DOCS.get(alias)
            name = NAMES.get(alias, alias)
            if doc_url:
                st.markdown(f"### [{name}]({doc_url})")
            else:
                st.subheader(name)
            desc = DESCRIPTIONS.get(alias)
            if desc:
                st.caption(desc)
            st.code(pretty_state(comp.state), language=None)
            for tr in transitions_by_alias.get(alias, []):
                label = f"{pretty_state(tr.from_state)} \u2192 {pretty_state(tr.to_state)}"
                key = f"{alias}_{tr.name}_{st.session_state.step_count}"
                if st.button(label, key=key, help=tr.name, type="primary"):
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

if sim.trace:
    st.divider()
    st.subheader("Recent trace")
    for entry in sim.trace[-10:]:
        step, name, component, from_s, to_s = entry
        if from_s != to_s:
            st.text(f"[{step:4d}] {NAMES.get(component, component)}: {pretty_state(from_s)} \u2192 {pretty_state(to_s)}")

if st.session_state.violations:
    st.divider()
    st.subheader("Invariant Violations")
    for v in st.session_state.violations:
        st.error(v)
