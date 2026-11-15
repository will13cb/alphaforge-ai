"""Third way to start (branch portefeuille_existant): the person enters what they already own, one holding at a time
(ticker or name + dollars). Stored in `S.existing_positions` = {ticker: dollars}; `profile.review` adds it to the
profile as `existing_positions`, and the engine (`dh.agents.existing`) reviews and rebuilds it. Nothing computed here."""

from __future__ import annotations

import streamlit as st

from dh import standins
from interface.core import services, validation, wizard
from interface.ui import components as ui

S = st.session_state

# A mostly Canadian account like the workshop's (slide 13), built ONLY from holdings we have data for: ZEQT.TO is
# left aside (a fund of funds we can't look into) and SPY stands where the account held a U.S. index fund.
# Suggested in the Assistant when the client entered a portfolio; `make warm` caches them (scripts/warm.py).
EXISTING_QUESTIONS = ["What do you think of my current portfolio?",
                      "What if I add 40,000 $ of XSP to my current portfolio?"]
EXAMPLE = {"RY.TO": 30_000, "TD.TO": 25_000, "ENB.TO": 20_000, "CNR.TO": 15_000, "XIU.TO": 60_000, "SPY": 20_000}


def _status(t: str, known: set[str]) -> str:
    si = standins.stand_in(t, known)
    if si is None:
        return "no market data, left out"
    return f"measured with {si['measured_with']}" + (" (currency hedge simulated)" if si["hedged"] else "")


def render() -> None:
    S.setdefault("existing_positions", {})
    pos: dict = S.existing_positions
    st.markdown('<p class="af-muted">Add each holding you already own: its ticker or name, and how many dollars are '
                'in it today. We check it with the same limits as our proposals, tell you what we see, and show how '
                'it could be rebuilt to fit you. Nothing is bought or sold.</p>', unsafe_allow_html=True)
    with st.form("af_add_holding", clear_on_submit=True, border=False):
        c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="bottom")
        name = c1.text_input("Ticker or name", placeholder="e.g. XIU.TO or Tesla")
        amount = c2.text_input("Dollars in it", placeholder="e.g. 25,000")
        added = c3.form_submit_button("Add", width="stretch")
    known = services.known_tickers()
    if added:
        chk = validation.held_position(name, amount)
        if not chk.ok:
            ui.error(chk.message)
        else:
            t, v = chk.value
            t = standins.canonical(t, known)          # "xsp" → XSP.TO
            pos[t] = pos.get(t, 0.0) + v
    if not pos:
        if st.button("Try an example portfolio (mostly Canadian)", width="stretch"):
            S.existing_positions = dict(EXAMPLE)
            st.rerun()
        return
    for t, v in list(pos.items()):
        a, b, c = st.columns([3, 2, 1], vertical_alignment="center")
        a.markdown(f"**{ui.esc(t)}**" + ("  ·  " + ui.esc(_status(t, known)) if known and t not in known else ""))
        b.markdown(f"{v:,.0f} $")
        if c.button("Remove", key=f"rm_{t}", width="stretch"):
            pos.pop(t)
            st.rerun()
    unknown = [t for t in pos if known and t not in known and _status(t, known).startswith("no market data")]
    if unknown:
        etfs = services.etfs_with_data()
        ui.notice(f"No market data for {', '.join(unknown)}: left out of the numbers. ETFs we have data for: "
                  + ", ".join(etfs) + ".", "warn")
    total = sum(pos.values())
    st.markdown(f"**Total: {total:,.0f} $** in {len(pos)} holding{'s' if len(pos) > 1 else ''}")
    if st.button("Continue: a few questions about you", type="primary", width="stretch"):
        S.setdefault("answers", {})
        S.answers["capital"] = wizard.from_profile({"capital": float(total)})["capital"]  # prefilled, can be edited
        S.goto = "Your profile"
        st.rerun()
