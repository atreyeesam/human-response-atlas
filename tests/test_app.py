from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def _radio(at, label):
    return next(r for r in at.radio if r.label == label)


def test_app_runs_without_errors():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    keys = {s.key for s in at.selectbox}
    if 'ask_drug' in keys:                      # downloaded data present
        # "Will this medicine work for me?" page
        drug = at.selectbox(key='ask_drug')
        drug.set_value(drug.options[0]).run()
        at.multiselect(key='ask_groups').set_value(['European', 'Oceanian']).run()
        assert not at.exception
        text = ' '.join(m.value for m in at.markdown)
        assert 'What this means for you' in text and 'doctor or pharmacist' in text
        # jump to the researcher view for the same medicine
        next(b for b in at.button if b.label.startswith('See the full evidence')).click().run()
        assert not at.exception
        assert at.radio(key='mode').value == 'Explore the evidence'
        _radio(at, 'Place studies by').set_value('Where the research team is based').run()
        assert not at.exception
        _radio(at, 'Colour the map by').set_value('Number of studies').run()
        assert not at.exception
        _radio(at, 'Data source').set_value('Demo (invented data)').run()
        assert not at.exception
    else:                                       # first run: welcome screen
        sample = next(b for b in at.button if b.label == 'Explore sample data')
        sample.click().run()
        assert not at.exception
        assert any('invented' in w.value for w in at.warning)
