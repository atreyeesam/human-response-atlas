import json

import anndata
import numpy as np
import pandas as pd

import alphagenome_atlas as ag


def test_spdi_and_hgvs_parsing():
    assert ag.parse_spdi('NC_000010.11:94781858:G:A') == {
        'chromosome': 'chr10', 'position': 94781859, 'ref': 'G', 'alt': 'A'}
    assert ag.parse_spdi('NC_000010.11:94781858:G:') is None            # deletion: not scored
    assert ag.parse_spdi('NT_187361.1:5:G:A') is None                   # not a primary chromosome
    rows = ag.variants_from_docsum('rs1', {'spdi': 'NC_000023.11:9:C:T,NC_000023.11:9:C:G'})
    assert [r['variant'] for r in rows] == ['chrX:10:C>T', 'chrX:10:C>G']
    rows = ag.variants_from_docsum('rs2', {'docsum': 'HGVS=NC_000019.10:g.44908822C>T,NG_007084.2:g.7903C>T'})
    assert [r['variant'] for r in rows] == ['chr19:44908822:C>T']


def test_rsids_ignore_star_alleles():
    a = pd.DataFrame({'variant': ['rs4244285', 'CYP2C19*2', 'rs12248560', 'rs4244285', 'HLA-B*57:01']})
    assert ag.rsids_from(a) == ['rs4244285', 'rs12248560']


def fake_get(url, data=None):
    ids = dict(x.split('=') for x in data.decode().split('&'))['id'].split('%2C')
    docs = {'4244285': {'spdi': 'NC_000010.11:94781858:G:A'},
            '12248560': {'spdi': 'NC_000010.11:94761899:C:T'}}
    return json.dumps({'result': {i: docs.get(i, {}) for i in ids}}).encode()


class FakeClient:
    calls = 0

    def scorer_metadata(self):
        return {'RNA_SEQ': type('M', (), {'is_signed': True})(), 'ATAC': type('M', (), {'is_signed': False})()}

    def query_variant(self, v, requested_scorers):
        FakeClient.calls += 1
        var = pd.DataFrame({'name': ['t1', 't2'], 'biosample_name': ['liver', 'heart']}, index=['0', '1'])
        rna = anndata.AnnData(X=np.array([[0.1, -2.0], [0.3, 0.2]], dtype=np.float32),
                              obs=pd.DataFrame({'gene_name': ['CYP2C19', 'CYP2C9']}, index=['0', '1']), var=var,
                              layers={'quantiles': np.array([[0.2, -0.97], [0.5, 0.4]], dtype=np.float32)})
        atac = anndata.AnnData(X=np.array([[0.5, 0.1]], dtype=np.float32), obs=pd.DataFrame(index=['0']), var=var)
        return {'RNA_SEQ': rna, 'ATAC': atac}


def test_run_maps_scores_and_resumes(tmp_path):
    a = pd.DataFrame({'variant': ['rs4244285', 'rs12248560', 'rs999', 'CYP2C19*17'],
                      'gene': ['CYP2C19', 'CYP2C19', 'X', 'CYP2C19']})
    m = ag.run('key', a, client=FakeClient(), get=fake_get, log=lambda *x: None, out=tmp_path)
    assert m['rsids_in_clinpgx'] == 3 and m['variants_scored'] == 2
    assert m['rsids_not_mappable_this_run'] == ['rs999']
    assert 'Output Terms of Use' in (tmp_path / 'NOTICE.txt').read_text()
    s = pd.read_csv(tmp_path / 'summary.csv').set_index('rsid')
    r = s.loc['rs4244285']
    assert r.variant == 'chr10:94781859:G>A'
    assert r.scorer == 'RNA_SEQ' and abs(r.max_score - 0.97) < 1e-3    # calibrated beats raw ATAC 0.5
    assert 'liver' in r['where'] or 'heart' in r['where']
    assert abs(r.max_score_for_annotated_gene - 0.97) < 1e-3
    before = FakeClient.calls
    ag.run('key', a, client=FakeClient(), get=fake_get, log=lambda *x: None, out=tmp_path)
    assert FakeClient.calls == before                                   # nothing fetched twice
    summary, manifest = ag.load(tmp_path)
    assert len(summary) == 2 and manifest['notice'].startswith('By using this information')


def test_failures_are_recorded_not_hidden(tmp_path):
    class Broken(FakeClient):
        def query_variant(self, v, requested_scorers):
            raise PermissionError('bad key')
    a = pd.DataFrame({'variant': ['rs4244285'], 'gene': ['CYP2C19']})
    m = ag.run('key', a, client=Broken(), get=fake_get, log=lambda *x: None, out=tmp_path)
    assert m['variants_scored'] == 0 and m['error_count_this_run'] == 1
    assert 'bad key' in m['errors_this_run'][0]['error']
