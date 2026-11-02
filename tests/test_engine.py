import json

import pytest

from hra import classify
from hra.dedup import deduplicate, norm_doi
from hra.engine import search_medicine
from hra.http import Http
from hra.models import FAILED, OK
from tests.hra_fixtures import FakeInternet


def run(name='clopidogrel', **kw):
    net = FakeInternet(**{k: kw.pop(k) for k in ('down', 'epmc_error') if k in kw})
    kw.setdefault('reviewed_path', None)
    return search_medicine(name, http=Http(transport=net, retries=1),
                           sources=('chembl', 'pubmed', 'europepmc', 'clinicaltrials'), **kw), net


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import hra.http
    monkeypatch.setattr(hra.http.time, 'sleep', lambda s: None)


def test_name_resolution_uses_exact_chembl_match_and_trade_names():
    res, _ = run('Plavix')
    ident = res.report['identity']
    assert ident['chembl_id'] == 'CHEMBL1771'          # moved from the salt to the parent
    assert ident['matched_chembl_id'] == 'CHEMBL1200'  # "Plavix" is filed under the salt
    assert ident['generic_name'] == 'clopidogrel'
    assert 'Plavix' in ident['trade_names']
    assert 'plavix' in res.report['search_names'] and 'clopidogrel' in res.report['search_names']
    assert 'sr-25990c' not in res.report['search_names']   # research codes are not used
    assert 'clopidogrel bisulfate' not in res.report['search_names']   # salt names add nothing
    assert res.report['search_names'][0] == 'clopidogrel'


def test_generic_name_also_collects_trade_names_from_salt_forms():
    res, _ = run('clopidogrel')
    assert 'Plavix' in res.report['identity']['trade_names']


def test_unknown_name_is_searched_as_typed():
    res, _ = run('fixtureunknownium')
    assert res.report['identity'] is None
    assert res.report['search_names'] == ['fixtureunknownium']


def test_cross_database_deduplication():
    res, _ = run()
    t = res.report['totals']
    assert t['records_retrieved'] == 4 + 3 + 2         # PubMed 4, Europe PMC 3, trials 2
    assert t['unique_studies'] == 5
    by_pmid = {p: s for s in res.studies for p in s.identifiers['pmid']}
    # PubMed 100 + Europe PMC MED:100 + trial NCT00000001 (registration in the paper) = one study
    assert {x['source'] for x in by_pmid['100'].sources} == {'pubmed', 'europepmc', 'clinicaltrials'}
    # preprint with the same title and year as PubMed 101 = same study
    assert {x['source'] for x in by_pmid['101'].sources} == {'pubmed', 'europepmc'}
    # trial NCT00000002 lists 103 as a RESULT (linked) and 102 only as BACKGROUND (not linked)
    assert 'NCT00000002' in by_pmid['103'].identifiers['nct']
    assert by_pmid['102'].identifiers['nct'] == []


def test_doi_normalisation():
    assert norm_doi('https://doi.org/10.1000/ABC') == norm_doi('doi:10.1000/abc') == '10.1000/abc'


def test_every_record_has_provenance():
    res, _ = run()
    for s in res.studies:
        assert s.sources and all(x['url'].startswith('https://') for x in s.sources)
    for e in res.extractions:
        assert e.quote and e.method and e.status and e.source_id
    rep = json.dumps(res.report)
    assert '"queries"' in rep and 'retrieved_at' in rep


def _counts(layer):
    return {k: v['count'] for k, v in layer.items()}


def test_population_and_geography_layers_stay_separate():
    res, _ = run()
    g = res.report['geography']
    assert _counts(g['1_registered_trial_sites (registry)']) == {'Bangladesh': 1, 'India': 1, 'China': 1}
    assert 'Bangladesh' in g['1b_recruitment_country_stated_in_abstract (rule-extracted, unverified)']
    assert 'United Kingdom' in g['2_author_affiliations']
    # "China/ethnology" describes origin, so it is not an indexed place
    assert 'China' not in g['3b_place_indexed_by_pubmed (not proof of recruitment)']
    pop = res.report['population']
    stated = pop['stated_population_descriptions (rule-extracted, unverified)']
    assert 'Bangladeshi patients' in stated and 'Han Chinese patients' in stated
    assert _counts(pop['registry_race_ethnicity_participants (ClinicalTrials.gov results, registry categories)']) == \
        {'Asian': 1150, 'White': 50}                   # the "Total" group, registry wording kept
    assert pop['studies_without_population_information'] >= 1


def test_ancestry_is_never_inferred_from_location_or_affiliation():
    res, _ = run()
    fields = {e.field for e in res.extractions}
    assert 'curated_ancestry_group' not in fields     # no ClinPGx here, so no ancestry at all
    for e in res.extractions:
        if e.field == 'stated_population':
            assert e.value.lower() in e.quote.lower()  # only what the text says
            assert e.status == 'unverified'


def test_efficacy_is_never_established_from_counts_alone():
    res, _ = run()
    e = res.report['evidence_categories']['efficacy']
    assert e['category'] == classify.NOT_ASSESSED and 'findings not yet evaluated' in e['reason']
    assert e['randomised_trials'] == 2 and e['reviews_or_meta_analyses'] == 1
    assert len(e['supporting']['studies']) == e['unique_studies']
    assert res.report['evidence_categories']['safety']['category'] == classify.LIMITED


def test_human_reviewed_conclusion_is_used_with_its_evidence(tmp_path):
    f = tmp_path / 'reviewed.csv'
    f.write_text('medicine,category,classification,supporting_pmids,summary,reviewer,reviewed_on\n'
                 'clopidogrel,efficacy,Established evidence,102;101,Consistent benefit,Dr Test,2026-10-31\n'
                 'clopidogrel,safety,Established evidence,,No evidence given,Dr Test,2026-10-31\n')
    res, _ = run(reviewed_path=f)
    e = res.report['evidence_categories']
    assert e['efficacy']['category'] == classify.ESTABLISHED and e['efficacy']['method'] == 'human-reviewed'
    assert e['efficacy']['supporting']['reviewed_pmids'] == ['102', '101']
    assert e['safety']['category'] == classify.LIMITED     # a conclusion without PMIDs is ignored


def ann(i, level, evidence=(), variant='rs1', outcome='Efficacy'):
    return {'id': str(i), 'level': level, 'url': f'https://www.clinpgx.org/x/{i}', 'variant': variant,
            'outcome': outcome, 'evidence': [{'pmid': p, 'significance': s} for p, s in evidence]}


def test_gene_rules():
    G = classify.gene_category
    guideline = {'level': 'A', 'provisional': False, 'guideline': 'G', 'guideline_url': 'https://g', 'pmids': ['1']}
    r = G([ann(1, '3')], guideline, OK)
    assert r['category'] == classify.ESTABLISHED and r['supporting'][0]['type'] == 'CPIC guideline'
    # a provisional CPIC level (no guideline) does not establish anything
    r = G([ann(1, '3')], {**guideline, 'provisional': True, 'guideline': ''}, OK)
    assert r['category'] == classify.LIMITED
    assert G([ann(1, '1B')], None, OK)['category'] == classify.ESTABLISHED
    assert G([ann(1, '2B')], None, OK)['category'] == classify.EMERGING
    assert G([ann(1, '4')], None, OK)['category'] == classify.LIMITED
    # conflict within one variant and outcome
    mixed = [('a', 'yes'), ('b', 'yes'), ('c', 'no'), ('d', 'no')]
    r = G([ann(1, '3', mixed)], None, OK)
    assert r['category'] == classify.CONFLICTING
    assert r['supporting'][0]['significant_pmids'] == ['a', 'b']
    assert r['supporting'][0]['non_significant_pmids'] == ['c', 'd']
    # positive for one variant and null for another is NOT a conflict
    r = G([ann(1, '3', [('a', 'yes'), ('b', 'yes')]), ann(2, '3', [('c', 'no'), ('d', 'no')], variant='rs2')],
          None, OK)
    assert r['category'] == classify.LIMITED
    assert G([], None, FAILED)['category'] == classify.NOT_ASSESSED


def test_registered_trials_without_results_are_not_efficacy_evidence():
    from hra.models import Study
    s = Study(key='nct:NCT1', title='t', year=2020, kind='trial',
              identifiers={'pmid': [], 'doi': [], 'pmcid': [], 'nct': ['NCT1']}, sources=[], categories=[],
              publication_types=[], countries=[], enrollment=10, registry_race_ethnicity=[], licence_notes=[])
    statuses = {'pubmed': OK, 'europepmc': OK, 'clinicaltrials': OK}
    r = classify.category_for('efficacy', [s], statuses)
    assert r['category'] == classify.NOT_FOUND and r['registered_trials_without_results'] == ['nct:NCT1']
    s.trial_has_results = True
    assert classify.category_for('efficacy', [s], statuses)['category'] == classify.LIMITED


def test_source_failure_never_becomes_a_zero_result():
    res, _ = run('fixtureunknownium', down={'www.ebi.ac.uk'})
    st = {s['source']: s for s in res.report['sources']}
    assert st['europepmc']['status'] == FAILED and 'simulated outage' in st['europepmc']['error']
    for v in res.report['evidence_categories'].values():
        assert v['category'] != classify.NOT_FOUND     # partial search can never say "not found"
    assert any('failed' in x for x in res.report['limitations'])


def test_europepmc_error_inside_http_200_is_a_failure():
    res, _ = run(epmc_error=True)
    st = {s['source']: s for s in res.report['sources']}
    assert st['europepmc']['status'] == FAILED and 'simulated bad request' in st['europepmc']['error']


def test_full_search_with_nothing_found_is_reported_as_not_found():
    res, _ = run('fixtureunknownium')
    assert res.report['evidence_categories']['safety']['category'] == classify.NOT_FOUND


def test_truncation_is_reported():
    res, _ = run()
    pm = next(s for s in res.report['sources'] if s['source'] == 'pubmed')
    assert pm['truncated'] is True and pm['total_hits_reported'] > pm['records_retrieved']


def test_search_is_reproducible(tmp_path):
    a, _ = run()
    b, _ = run()
    assert a.report['fingerprint'] == b.report['fingerprint']
    strip = lambda r: {k: v for k, v in r.items() if k not in ('started_at', 'finished_at', 'sources')}  # noqa
    assert json.dumps(strip(a.report), sort_keys=True, default=str) == json.dumps(strip(b.report), sort_keys=True, default=str)
    d = a.write_report(tmp_path)
    for f in ('report.json', 'studies.csv', 'extractions.csv', 'sources.csv', 'report.html'):
        assert (d / f).exists()
    html = ' '.join((d / 'report.html').read_text().split())
    assert 'Exact search terms' in html and 'not proof that research does not exist' in html
    assert 'CC BY-NC-SA 4.0' in html and 'CC BY-SA 3.0' in html
    rep = json.loads((d / 'report.json').read_text())
    assert all('abstract' not in st for st in rep['studies'])          # no full abstracts stored
    assert all(len(e.quote) <= 300 for e in a.extractions)            # only short excerpts


def test_report_makes_no_individual_claims(tmp_path):
    res, _ = run()
    text = (res.write_report(tmp_path) / 'report.html').read_text().lower()
    for banned in ('will work for you', 'safe for you', 'recommended dose', 'you should take'):
        assert banned not in text


def test_engine_is_usable_without_streamlit():
    import sys
    res, _ = run()
    assert res.report['totals']['unique_studies'] > 0
    assert 'streamlit' not in {m.split('.')[0] for m in sys.modules if m.startswith('hra')}


def test_dedup_handles_empty():
    assert deduplicate([]) == []


def test_unknown_ancestry_is_not_counted_as_population_information(tmp_path, monkeypatch):
    import ingest
    import atlas
    from tests import fixtures
    monkeypatch.setattr(ingest, "_get", fixtures.fake_get)
    ingest.run(tmp_path / "live", log=lambda *_: None, pubmed_cache=tmp_path / "p.json")
    data = atlas.load_live(tmp_path / "live")
    sp = data["study_populations"]
    sp.loc[sp.pmid == "33333", "population"] = "Unknown"
    res = search_medicine('drugx', clinpgx_data=data, sources=('clinpgx',))
    pop = res.report['population']
    assert pop['studies_without_population_information'] >= 1
    assert res.report['evidence_categories']['efficacy']['category'] == 'Not assessed'


def test_every_claim_traces_to_evidence():
    res, _ = run()
    integ = res.report['integrity']
    assert integ['passed'], integ['problems']
    assert integ['checked_claims'] > 10


def test_audit_catches_unsupported_claims():
    import copy
    from hra.audit import audit
    res, _ = run()
    bad = copy.deepcopy(res.report)
    layer = bad['geography']['2_author_affiliations']
    first = next(iter(layer))
    layer[first]['count'] += 1                                  # inflate a count
    bad['population']['stated_population_descriptions (rule-extracted, unverified)']['Made-up group'] = \
        {'count': 1, 'unit': 'studies', 'evidence': ['pmid:000']}   # cite a study that is not there
    bad['evidence_categories']['safety']['supporting']['studies'] = []
    out = audit(bad, res.studies, res.extractions)
    assert not out['passed'] and len(out['problems']) >= 3
    ex = copy.deepcopy(res.extractions)
    e = next(x for x in ex if x.field == 'stated_sample_size')
    e.value = '99999'
    assert not audit(res.report, res.studies, ex)['passed']
