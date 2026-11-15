"""A simple bond plan first, with pricing and source details available below it."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_plan(plan: dict) -> None:
    if plan['status'] == 'unavailable':
        st.warning(plan['message'])
    else:
        bond = plan['selected_bond']
        st.subheader(f"100% {bond['issuer']}")
        a, b, c = st.columns(3)
        a.metric('Requested annual rate', f"{plan['requested_rate_pct']:g}%")
        b.metric('Fixed annual rate' if bond.get('instrument_type') in ('gic', 'cd') else 'Fixed coupon', f"{bond['coupon_pct']:g}%")
        c.metric('Maturity', bond['maturity'])
        st.caption('Bond identified. A current purchase quote is needed to confirm the return on your invested cash.')
        if bond.get('cashflow_type') == 'compound_at_maturity':
            st.write(f"Illustrative interest at maturity: **{plan['total_interest']:,.0f} {plan['currency']}**. Interest compounds annually; no annual cash payout.")
        else:
            st.write(f"Illustrative income: **{plan['annual_interest']:,.0f} {plan['currency']} per year**. "
                     'Held to maturity; interest is paid out, not reinvested.')
        if plan['currency'] == 'USD':
            st.info('This bond pays in USD. Its CAD value can change with the exchange rate.')
        with st.expander('Payments, price assumptions and sources'):
            st.write(f"Principal repaid at maturity: {plan['principal_at_maturity']:,.0f} {plan['currency']}, if the issuer pays as agreed.")
            st.markdown('\n'.join(f'- {a}' for a in plan['assumptions']))
            st.dataframe(pd.DataFrame(plan['schedule']), hide_index=True, width='stretch')
            st.link_button('Instrument terms', bond['terms_source'])
            if bond.get('quote_source'):
                st.link_button('Offer source', bond['quote_source'])
                st.caption(f"Offer dated {bond.get('quote_as_of', 'not supplied')}; confirm the current offer with the issuer or broker.")
            st.caption(f"Terms dated {bond.get('terms_as_of', 'not supplied')} · ID {bond.get('instrument_id', bond.get('isin', 'not supplied'))}")
    refs = plan['references']
    with st.expander('Canada and U.S. fixed-income catalogue'):
        rows = refs.get('outstanding_bonds', [])
        st.caption(f"{len(rows)} loaded instruments · {refs.get('source_mode', 'reference')}. Reference data does not confirm broker inventory.")
        if rows:
            frame = pd.DataFrame(rows)
            columns = [c for c in ('issuer', 'country', 'currency', 'instrument_type', 'maturity', 'coupon_pct',
                                   'benchmark_yield_pct', 'auction_yield_pct', 'yield_as_of', 'terms_as_of') if c in frame]
            query = st.text_input('Find a bond or fixed-income instrument', key='fixed_income_search')
            if query:
                frame = frame[frame.astype(str).apply(lambda c: c.str.contains(query, case=False, regex=False)).any(axis=1)]
            st.dataframe(frame[columns], hide_index=True, width='stretch')
        st.caption('Coupon = interest on face value. Yield = return implied by a price. Auction yields are historical auction results, not current offers.')
        if refs.get('quality_issues'):
            st.warning(f"{len(refs['quality_issues'])} invalid catalogue records were excluded. See quality_report.csv for details.")
        if refs.get('coverage'):
            st.caption(refs['coverage'])
