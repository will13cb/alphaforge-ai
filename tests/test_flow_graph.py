"""The live pipeline graph: built only from recorded hand-offs."""
from interface.ui import flow


def test_working_node_is_the_last_receiver_and_finishing_clears_it():
    steps = [{"agent": "Client", "to": "Profiler"}, {"agent": "Profiler", "to": "Market data"},
             {"agent": "Market data", "to": "Portfolio"}, {"agent": "Portfolio", "to": "Guardian"}]
    runs, used, working = flow.state(steps)
    assert working == "Guardian" and runs["Portfolio"] == 1 and ("Portfolio", "Guardian") in used
    assert flow.state(steps, finished=True)[2] is None
    assert flow.state([])[2] == "Profiler"


def test_repeat_runs_counted_and_unknown_agents_ignored(monkeypatch):
    monkeypatch.setenv("AF_LANG", "en")
    steps = [{"agent": "Guardian", "to": "Critic"}, {"agent": "Guardian", "to": "Client"},
             {"agent": "Fixed-income agent", "to": "Client"}, {"agent": "Trace store", "to": "Amazon S3"}]
    runs, _, _ = flow.state(steps, finished=True)
    assert runs["Guardian"] == 2 and "Fixed-income agent" not in runs and runs["Trace store"] == 1
    html = flow.svg(steps, finished=True)
    assert "×2" in html and "<svg" in html and "All steps recorded." in html


def test_french_labels_stay_inside_their_boxes(monkeypatch):
    """Longer French labels ran out of their box: titles wrap, subtitles shrink, the Guardian's box grows."""
    monkeypatch.setenv("AF_LANG", "fr")
    labels, (pos, size, height) = flow._labels(), flow._layout()
    assert labels["Market data"][0] == ["Données", "de marché"] and labels["Client"][0] == ["Client"]
    assert size["Guardian"][0] > flow.NW and size["Client"][0] == flow.NW
    for name, (lines, sub) in labels.items():
        room = size[name][0] - 2 * flow.PAD
        assert all(flow._width(t, flow._fit(t, flow.T_SIZE, room, True), True) <= room + .5 for t in lines), name
        assert flow._width(sub, flow._fit(sub, flow.S_SIZE, room)) <= room + .5, name
    assert pos["Guardian"][1] + size["Guardian"][1] < height
    html = flow.svg([], finished=True)
    assert "règles imposées par le code" in html and "Toutes les étapes sont enregistrées." in html


def test_a_label_left_by_the_other_language_maps_back_to_its_option():
    """Streamlit returns a choice as its displayed label; after a language switch it is the other language's."""
    from dh import i18n
    sections = ["Welcome", "Your profile", "Your results"]
    assert i18n._to_option(i18n.tr("Welcome", to="fr"), sections, None) == "Welcome"
    assert i18n._to_option("Your profile", sections, None) == "Your profile"
    assert i18n._to_option([i18n.tr("Welcome", to="fr"), "typed by hand"], sections, None) == ["Welcome", "typed by hand"]
    assert i18n._to_option(3, [1, 2, 3], None) == 3 and i18n._to_option(None, sections, None) is None
