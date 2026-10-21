from pathlib import Path
import json
from streamlit.testing.v1 import AppTest
from sensorforge.catalog import DEFAULT_DB, validate_options
from sensorforge.config import ROOT


def launch(monkeypatch):
    # UI tests cannot overwrite or depend on the owner's current SQLite data.
    options=validate_options(json.loads((DEFAULT_DB.parent/'demo_options.json').read_text()))
    monkeypatch.setattr('sensorforge.optimizer_ui.read_catalog',lambda:options)
    return AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()


def button(app,label):
    return next(widget for widget in app.button if widget.label==label)


def field(widgets,label):
    return next(widget for widget in widgets if widget.label==label)


def test_catalogue_app_pages_no_training_or_upload(monkeypatch):
    app=launch(monkeypatch)
    assert not app.exception
    assert any('DEMONSTRATION DATA' in w.value for w in app.warning)
    assert not app.get('file_uploader')
    assert not any('train' in b.label.lower() for b in app.button)
    for page in app.sidebar.radio[0].options:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception,page


def test_optimization_results_and_changed_search_space(monkeypatch):
    app=launch(monkeypatch)
    button(app,'Optimize designs').click().run(timeout=60)
    assert not app.exception
    result=app.session_state['optimization_result']
    assert not result.table.empty
    assert result.report['globally_verified']
    assert len(app.get('plotly_chart'))>=2
    field(app.multiselect,'Allowed fillers').set_value([]).run()
    assert not app.exception
    assert any('settings or catalogue have changed' in x.value for x in app.info)
    button(app,'Optimize designs').click().run(timeout=60)
    assert not app.exception
    assert all(app.session_state['optimization_result'].table.constituents==1)


def test_infeasible_and_exact_count_and_real_data_filter(monkeypatch):
    app=launch(monkeypatch)
    field(app.selectbox,'Combination size mode').set_value('Exactly this many constituents')
    field(app.number_input,'Minimum / exact constituent count').set_value(3)
    field(app.number_input,'Minimum sensitivity (kPa⁻¹)').set_value(1.)
    button(app,'Optimize designs').click().run(timeout=60)
    assert not app.exception
    assert app.session_state['optimization_result'].table.empty
    assert app.session_state['optimization_result'].report['minimum']==3
    assert any('No combination satisfies' in w.value for w in app.warning)
    field(app.selectbox,'Evidence scope').set_value('Exclude demonstration entries').run()
    assert not app.exception
    assert any('not yet installed experimental' in x.value for x in app.info)
