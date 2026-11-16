"""French client text must survive extraction, numeric grounding, and form prefill."""
from pathlib import Path

import pytest

from dh.agents import extractor as x
from dh.agents.scenarios import AMIRA

FRENCH_AMIRA_TEXT = """Je m’appelle Amira et j’ai 26 ans. Mon revenu est stable et mon fonds d’urgence couvre six mois de dépenses. Je préfère ne pas préciser mon secteur d’emploi.

Je souhaite faire fructifier mon épargne sur 15 ans. J’ai 30 000 $ à investir aujourd’hui et je peux ajouter 500 $ par mois. Je n’ai pas de montant cible précis. Je ne prévois aucun retrait dans les trois prochaines années : la part à réserver pour ces retraits est donc de 0 %.

Si mon portefeuille perdait 20 % en trois mois, j’investirais davantage pendant que les prix sont bas. Je peux accepter une baisse maximale de 40 % entre un sommet et le point le plus bas du portefeuille pendant la durée de mon investissement.

Mes connaissances sont intermédiaires et j’investis depuis quatre ans. J’ai déjà détenu des actions, des FNB et des cryptomonnaies. Pour un placement ayant autant de chances de gagner 25 % que de perdre 5 %, ma réponse à la question du rendement moyen est 10 %.

Pour les trois choix entre un placement incertain et une somme garantie :
- Sur 10 000 $, avec autant de chances de gagner 25 % que de perdre 5 %, le rendement garanti minimal que j’accepterais à la place est 8,3 %, soit 10 830 $ après un an.
- Sur 10 000 $, avec autant de chances de gagner 40 % que de perdre 10 %, j’accepterais au minimum 10,3 % garantis, soit 11 030 $ après un an.
- Sur 100 000 $, avec autant de chances de terminer à 120 000 $ qu’à 95 000 $, j’accepterais au minimum 106 300 $ garantis, soit 6,3 %.
Je souhaite un portefeuille de marché diversifié, et non une solution composée uniquement d’obligations à taux fixe. Je m’intéresse à l’intelligence artificielle et aux cryptomonnaies. Je n’ai aucune exclusion et je n’impose aucun titre ni pourcentage particulier."""


@pytest.fixture(autouse=True)
def no_external_cache_or_automatic_download(monkeypatch, tmp_path):
    monkeypatch.setattr(x, "DEMO_CACHE", tmp_path / "demo")
    monkeypatch.setattr(x, "LOCAL_CACHE", tmp_path / "local")
    monkeypatch.delenv("AF_AUTO_DATA", raising=False)


def assert_amira_profile(result):
    assert result["missing"] == []
    p = result["profile"]
    for field in ("name", "age", "horizon_years", "objective", "capital", "monthly_contribution",
                  "emergency_fund_months", "income_stability", "withdrawal_share_3y", "loss_reaction",
                  "max_loss_pct", "knowledge_level", "years_experience", "ev_answer_pct"):
        assert p[field] == AMIRA[field], field
    for field in ("products_held", "interests", "exclusions"):
        assert set(p.get(field, [])) == set(AMIRA[field]), field
    assert p["kyc_bets"] == pytest.approx(AMIRA["kyc_bets"])
    assert p.get("investment_mode", "market") == "market"
    for field in ("target_amount", "requested_positions", "employment_sector", "fixed_rate_pct"):
        assert not p.get(field), field


def test_complete_french_amira_profile_is_extracted_offline():
    result = x.extract(FRENCH_AMIRA_TEXT, provider="mock")
    assert result["source"] == "rules"
    assert_amira_profile(result)


def test_bedrock_failure_preserves_complete_french_rules_fallback(monkeypatch):
    def unavailable(_):
        raise RuntimeError("Bedrock temporarily unavailable")

    monkeypatch.setattr(x, "_run_agent", unavailable)
    result = x.extract(FRENCH_AMIRA_TEXT, provider="bedrock")
    assert result["source"] == "rules"
    assert "Bedrock temporarily unavailable" in result["note"]
    assert_amira_profile(result)


@pytest.mark.parametrize("space", [" ", "\u00a0", "\u202f"])
def test_french_grouped_amounts_decimal_commas_and_word_numbers_are_grounded(space):
    text = (f"J’ai 30{space}000 $, puis 106{space}300 $. Les taux sont 8,3 %, 10,3 % et 6,3 %. "
            "Mon fonds couvre six mois; j’investis depuis quatre ans et ma réponse est dix pour cent.")
    assert {30_000, 106_300, 8.3, 10.3, 6.3, 6, 4, 10} <= x.numbers_in(text)


def test_french_spelled_thousands_ground_amount_without_inventing_a_number():
    p, notes = x.validate({"capital": 30_000, "emergency_fund_months": 6, "years_experience": 4},
                          "J’ai trente mille dollars, six mois de réserve et quatre ans d’expérience.")
    assert p == {"capital": 30_000, "emergency_fund_months": 6, "years_experience": 4}
    assert not notes


def test_validator_accepts_stated_french_kyc_percentages_and_average_answer():
    p, notes = x.validate({"kyc_bets": dict(AMIRA["kyc_bets"]), "ev_answer_pct": 10}, FRENCH_AMIRA_TEXT)
    assert p["kyc_bets"] == pytest.approx(AMIRA["kyc_bets"])
    assert p["ev_answer_pct"] == 10
    assert not notes


def test_validator_rejects_invented_kyc_answers_and_unsupported_bet_options():
    p, notes = x.validate({"kyc_bets": {"bet_small": .09, "bet_large": .103, "unknown_bet": .083},
                           "ev_answer_pct": 11}, "Le premier choix est 9 %; ma réponse moyenne est 10 %.")
    assert not p.get("kyc_bets")
    assert "ev_answer_pct" not in p
    assert notes


def test_french_extracted_profile_prefills_every_required_wizard_step():
    from interface.core import wizard

    p = x.extract(FRENCH_AMIRA_TEXT, provider="mock")["profile"]
    raw_answers = wizard.from_profile(p)
    for step in range(len(wizard.STEPS)):
        _, errors = wizard.check_step(step, raw_answers)
        assert not errors, (step, errors)
    values, errors = wizard.all_values(raw_answers)
    assert not errors
    back = wizard.to_profile(values)
    assert x.missing(back) == []
    assert back["kyc_bets"] == pytest.approx(AMIRA["kyc_bets"])
    assert back["ev_answer_pct"] == 10


def test_pasting_french_profile_into_welcome_prefills_age_and_emergency_fund(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("AF_LANG", "en")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "interface" / "app.py"),
                            default_timeout=30).run()
    assert not app.exception
    app.text_area(key="welcome_text").set_value(FRENCH_AMIRA_TEXT).run()
    next(button for button in app.button if button.label == "Continue with my text").click().run()
    assert not app.exception
    assert app.session_state["section"] == "Your profile"
    assert app.text_input(key="f_age").value == "26"
    assert app.text_input(key="f_emergency_fund_months").value == "6"
    assert app.session_state["free_text_notes"]["missing"] == []


def test_successful_bedrock_extraction_is_completed_from_explicit_french_facts(monkeypatch):
    monkeypatch.setattr(x, "_run_agent", lambda text: ({"name": "Amira", "capital": 30000, "income_stability": "stable"}, 1))
    result = x.extract(FRENCH_AMIRA_TEXT, provider="bedrock")
    assert result["source"] == "bedrock" and result["failure_type"] == ""
    assert "age" in result["supplemented_fields"]
    assert_amira_profile(result)


def test_quiz_stories_stay_separate_when_text_is_pasted_as_one_paragraph():
    result = x.extract(" ".join(FRENCH_AMIRA_TEXT.split()), provider="mock")
    assert_amira_profile(result)


def test_hypothetical_quiz_capital_does_not_fill_missing_actual_capital():
    text = FRENCH_AMIRA_TEXT.replace("J’ai 30 000 $ à investir aujourd’hui et je peux ajouter 500 $ par mois.",
                                    "Je peux ajouter 500 $ par mois.")
    result = x.extract(text, provider="mock")
    assert "capital" not in result["profile"]
    from interface.core import wizard
    assert "capital" not in wizard.from_profile(result["profile"])


def test_hypothetical_losses_do_not_replace_missing_client_loss_tolerance():
    import re
    text = re.sub(r"Je peux accepter une baisse maximale.*?mon investissement\.", "", FRENCH_AMIRA_TEXT)
    result = x.extract(text, provider="mock")
    assert "max_loss_pct" not in result["profile"]
    assert "max_loss_pct" in result["missing"]
