import csv

import pandas as pd
import pytest

from hra import benchmark
from hra.models import Extraction, Record
from tests.test_engine import run


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import hra.http
    monkeypatch.setattr(hra.http.time, 'sleep', lambda s: None)


def test_prf():
    assert benchmark.prf(3, 1, 1) == {'tp': 3, 'fp': 1, 'fn': 1, 'precision': 0.75, 'recall': 0.75, 'f1': 0.75}
    assert benchmark.prf(0, 0, 0)['precision'] is None


def test_descriptor_groups_are_benchmark_only_and_word_bounded():
    assert benchmark.descriptor_groups('Han Chinese patients') == {'East Asian'}
    assert 'European' in benchmark.descriptor_groups('Caucasian subjects')
    assert benchmark.descriptor_groups('whitecoat effect') == set()


def test_search_completeness_against_a_reference_set():
    res, _ = run()
    a = benchmark.completeness({'100', '101', '999'}, res)
    assert a['reference_studies'] == 3
    assert a['recall_any_query'] == round(2 / 3, 3)
    assert a['missed_sample'] == ['999'] and a['missed_total'] == 1


def test_dedup_benchmark_hides_identifiers_and_relinks_by_title():
    res, _ = run()
    b = benchmark.dedup_benchmark(res.records)
    assert b['known_duplicate_pmids'] >= 1          # PMID 100 is in PubMed and Europe PMC
    t = b['title_matching_with_ids_hidden']
    assert t['tp'] >= 1 and t['fp'] == 0


def test_extraction_vs_curation():
    pub = Record('pubmed', '1', '', 'publication', title='t', pmid='1', abstract='x' * 300)
    class R:   # minimal stand-in for a SearchResult
        records = [pub]
        studies = [type('S', (), {'key': 'pmid:1', 'identifiers': {'pmid': {'1'}}})()]
        extractions = [Extraction('pmid:1', 'stated_sample_size', '412', 'pubmed', '1', 'q', 'a', 'rule'),
                       Extraction('pmid:1', 'stated_sample_size', '37', 'pubmed', '1', 'q', 'a', 'rule'),
                       Extraction('pmid:1', 'stated_population', 'Han Chinese', 'pubmed', '1', 'q', 'a', 'rule')]
    sp = pd.DataFrame({'pmid': ['1', '1'], 'study_cases': [200, 212], 'study_controls': [None, None],
                       'population': ['East Asian', 'European']})
    ref = benchmark.curated_reference({'study_populations': sp}, {'1'})
    assert ref['1']['groups'] == {'East Asian', 'European'}
    c = benchmark.extraction_vs_curation(R, ref)
    assert c['sample_size']['tp'] == 0 and c['sample_size']['fn'] == 1   # 412 is not 200 or 212
    assert c['population']['tp'] == 1 and c['population']['fn'] == 1


def test_worksheet_round_trip(tmp_path):
    res, _ = run()
    ws = benchmark.write_worksheet([res], 3, tmp_path, min_abstract=20)
    rows = list(csv.DictReader(open(ws)))
    assert rows and all(r['gold_sample_sizes'] == '' for r in rows)       # blinded: no predictions
    assert 'stated_' not in ws.read_text()
    preds = list(csv.DictReader(open(tmp_path / 'predictions_hidden.csv')))
    # a reviewer annotates exactly what the rules predicted for one abstract -> perfect scores
    target = rows[0]['pmid']
    mine = [p for p in preds if p['pmid'] == target]
    for r in rows:
        r['reviewer'] = 'AS' if r['pmid'] == target else ''
        if r['pmid'] == target:
            for field, col in [('stated_sample_size', 'gold_sample_sizes'),
                               ('stated_population', 'gold_populations'),
                               ('stated_recruitment_country', 'gold_recruitment_countries'),
                               ('stated_effect_estimate', 'gold_effect_estimates')]:
                r[col] = ';'.join(p['value'] for p in mine if p['field'] == field)
    with open(ws, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    s = benchmark.score(ws)
    assert s['annotated_abstracts'] == 1
    for v in s['fields'].values():
        assert v['fp'] == 0 and v['fn'] == 0


def test_scoring_counts_misses_and_false_alarms(tmp_path):
    ws, pred = tmp_path / 'w.csv', tmp_path / 'predictions_hidden.csv'
    ws.write_text('pmid,medicine,title,abstract,gold_sample_sizes,gold_populations,'
                  'gold_recruitment_countries,gold_effect_estimates,reviewer,notes\n'
                  '1,m,t,a,"1,200;80",Han Chinese,China,OR 2.5,AS,\n')
    pred.write_text('pmid,field,value,method\n1,stated_sample_size,1200,r\n1,stated_sample_size,15,r\n'
                    '1,stated_recruitment_country,Japan,r\n')
    f = benchmark.score(ws)['fields']
    assert (f['stated_sample_size']['tp'], f['stated_sample_size']['fp'], f['stated_sample_size']['fn']) == (1, 1, 1)
    assert f['stated_population']['fn'] == 1
    assert f['stated_recruitment_country']['fp'] == 1 and f['stated_recruitment_country']['fn'] == 1
    assert f['stated_effect_estimate']['recall'] == 0.0
