"""French display fixes preserve calculations, raw records and English mode."""
import copy

import altair as alt
import pandas as pd
import pytest

from dh import i18n
from interface.ui import flow, theme


@pytest.fixture(autouse=True)
def french(monkeypatch):
    monkeypatch.setattr(i18n, 'lang', lambda: 'fr')


def test_nested_html_translates_complete_sentences_and_keeps_attributes():
    source = '<div style="width:40%"><b>Benefits</b><p>About 5 minutes, one topic at a time, with help on each question.</p></div>'
    result = i18n.tr(source)
    assert 'Avantages' in result and 'un sujet à la fois' in result
    assert 'width:40%' in result and 'About' not in result
    assert i18n.tr('An unfamiliar sentence and a brand name.') == 'An unfamiliar sentence and a brand name.'


def test_commands_and_tickers_are_never_translated():
    assert '`make data`' in i18n.tr('Use `make data` to load data.')
    assert '`make data-stress`' in i18n.tr('data/raw_stress/ is missing: run `make data-stress` (needs internet)')
    assert 'XIU.TO' in i18n.tr('XIU.TO: worst drop -15.7%')


def test_tables_are_translated_copies_with_original_numbers():
    original = pd.DataFrame({'Holding':['Gold fund (GLD)'],'Share':[.225]})
    before = original.copy(deep=True)
    display = i18n._table_text(original)
    assert list(display.columns) == ['Placement','Part']
    assert display.iloc[0, 1] == .225
    pd.testing.assert_frame_equal(original,before)
    records = i18n._table_text([{'rule':'G4','status':'pass','detail':'all essentials known'}])
    assert list(records.columns) == ['Règle','Résultat','Détail']


def test_chart_labels_and_locale_preserve_field_names_and_numeric_data():
    chart = alt.Chart(pd.DataFrame({'strategy':['Broad core'],'value':[1234.5]})).mark_bar().encode(
        x=alt.X('value:Q',title='Worst drop'),y=alt.Y('strategy:N',title=None))
    before=chart.to_dict()
    translated=i18n.chart_spec(before)
    assert translated['encoding']['x']['field']=='value'
    assert translated['encoding']['x']['title']=='Baisse maximale'
    assert next(iter(translated['datasets'].values()))[0]['value']==1234.5
    assert translated['config']['locale']['number']['decimal']==','
    assert before['encoding']['x']['title']=='Worst drop'
    assert theme.style_chart(chart).to_dict()['encoding']['x']['title']=='Baisse maximale'


def test_pipeline_graph_translates_labels_without_changing_node_ids():
    svg=flow.svg([],finished=True)
    from xml.etree import ElementTree
    start, end = svg.index('<svg'), svg.index('</svg>') + len('</svg>')
    labels = ' '.join(ElementTree.fromstring(svg[start:end]).itertext())
    assert 'Profileur' in labels and 'Données de marché' in labels and 'vos réponses' in labels
    assert flow.NODES[1][0]=='Profiler'


def test_english_is_unchanged(monkeypatch):
    monkeypatch.setattr(i18n,'lang',lambda:'en')
    text='Benefits: worst drop -15.7%'
    assert i18n.tr(text)==text
    original={'encoding':{'x':{'field':'value','title':'Worst drop'}}}
    assert i18n.chart_spec(original)==original
