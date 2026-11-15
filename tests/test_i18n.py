"""Français ⇄ English (decision #49): the switch, the translation table, and both apps in French."""
import sys
from pathlib import Path

import pytest

from dh import i18n
from dh.i18n_fr import EXACT, PHRASES

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


def test_tr_exact_phrases_and_untouched_engine_text():
    assert i18n.tr("Run the analysis", to="fr") == "Lancer l'analyse"
    assert i18n.tr("  Run the analysis ", to="fr").strip() == "Lancer l'analyse"
    assert i18n.tr("Your limits, Robert", to="fr") == "Vos limites, Robert"
    engine = "loss limit = smaller of the drop you'd accept (15%) and what your situation allows"
    assert i18n.tr(engine, to="fr").startswith("limite de perte = la plus petite")   # engine text in French too (#49)
    assert i18n.tr("Run the analysis", to="en") == "Run the analysis"
    assert i18n.tr(None, to="fr") is None and i18n.tr(3, to="fr") == 3


def test_table_has_no_empty_or_identical_long_entries():
    for d in (EXACT, PHRASES):
        assert all(v.strip() for v in d.values())
    assert not [k for k, v in EXACT.items() if len(k) > 30 and k == v]


@pytest.mark.parametrize("app", ["interface/app.py", "app/app.py"])
def test_apps_render_in_french_and_switch_to_english(app, monkeypatch):
    monkeypatch.setenv("AF_LANG", "fr")
    at = AppTest.from_file(str(ROOT / app), default_timeout=180).run()
    assert not at.exception
    assert at.session_state[i18n.STATE_KEY] == "fr"
    at.radio(key=i18n.STATE_KEY).set_value("en").run()
    assert not at.exception and at.session_state[i18n.STATE_KEY] == "en"


def test_guided_interface_welcome_is_french(monkeypatch):
    monkeypatch.setenv("AF_LANG", "fr")
    at = AppTest.from_file(str(ROOT / "interface" / "app.py"), default_timeout=180).run()
    texts = [b.label for b in at.button] + [m.value for m in at.markdown]
    assert "Commencer les questions" in texts or any("Commencer" in t for t in texts)
    assert "Start the questions" not in texts


def test_explainer_in_french_passes_the_guardian(monkeypatch, tmp_path):
    """French mode: the deterministic explanation is French, ends with the French disclaimer, and G11-G13 pass."""
    from dh.agents import explainer
    from dh.agents.profiler import derive_limits
    from dh.personas import DISCLAIMER_FR
    from test_explainer import ROBERT_TSLA, STRATS
    monkeypatch.setattr(explainer, "DEMO_CACHE", tmp_path / "d")
    monkeypatch.setattr(explainer, "LOCAL_CACHE", tmp_path / "l")
    monkeypatch.setenv("AF_LANG", "fr")
    lim = derive_limits(ROBERT_TSLA)
    e = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="mock")
    assert e["source"] == "template" and e["verdict"] == "pass", e["checks"]
    assert DISCLAIMER_FR in e["text"] and "voici ce que cette simulation a trouvé" in e["text"] and "TSLA" in e["text"]
    monkeypatch.setenv("AF_LANG", "en")
    en = explainer.explain(STRATS, lim, ROBERT_TSLA, provider="mock")
    assert en["facts_hash"] != e["facts_hash"] and "here is what this simulation found" in en["text"]


def test_engine_sentences_translate_and_keep_numbers():
    s = "observed worst drop 15.7% (2021-2026) vs your 15% loss limit: what happened, not a guarantee"
    fr = i18n.tr(s, to="fr")
    assert fr.startswith("pire baisse observée 15,7") and "limite de perte de 15" in fr
    assert i18n.tr_words(s).startswith("pire baisse observée 15.7%")         # numbers untouched for G12
    assert i18n.tr('<div style="width:40%">x</div>', to="fr") == '<div style="width:40%">x</div>'   # never inside tags
