import os
import pytest
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


def test_app_runs_without_exception():
    at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 4
    assert any("Probabilité d'atteindre" in m.label for m in at.metric)


@pytest.mark.parametrize("product", ["Reverse convertible à barrière", "Capital protégé"])
def test_structured_branches(product):
    at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=120).run()
    radio = next(r for r in at.radio if "Autocall / Phoenix" in r.options)
    radio.set_value(product).run()
    assert not at.exception, [e.value for e in at.exception]


def test_simulated_portfolio_tab_and_tax_tab_render():
    at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=120).run()
    assert not at.exception
    assert any("Rendement annualisé" in m.label for m in at.metric)
    assert any("Gain réalisé" in n.label for n in at.number_input)
