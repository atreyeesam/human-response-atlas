import json

import pandas as pd
import pytest

import atlas
import ingest
from tests import fixtures


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "_get", fixtures.fake_get)
    out = tmp_path / "live"
    ingest.run(out, log=lambda *_: None, pubmed_cache=tmp_path / "cache" / "pubmed.json")
    return out


def test_ingest_writes_outputs_and_manifest(live):
    for name in ["associations.csv", "evidence.csv", "study_populations.csv",
                 "cpic_pairs.csv", "cpic_publications.csv", "manifest.json"]:
        assert (live / name).exists(), name
    m = json.loads((live / "manifest.json").read_text())
    assert m["sources"]["clinpgx"]["summaryAnnotations"]["release_date"] == "2026-10-01"
    assert m["sources"]["clinpgx"]["summaryAnnotations"]["url"].startswith("https://api.clinpgx.org/")
    assert m["sources"]["cpic"]["release"] == "v9.9.9"
    assert m["licences"]["clinpgx"]["short"] == "CC BY-NC-SA 4.0"
    assert m["licences"]["clinpgx"]["noncommercial"] is True
    assert m["accessed_utc"]
    # licence text shipped inside the download is preserved verbatim
    assert (live / "upstream_licences" / "clinpgx_summaryAnnotations_LICENSE.txt").exists()


def test_associations_split_drugs_and_join_cpic(live):
    a = pd.read_csv(live / "associations.csv", dtype=str, keep_default_na=False)
    assert set(a[a.summary_annotation_id == "900002"].drug) == {"drugx", "drugy"}
    row = a[(a.summary_annotation_id == "900001")].iloc[0]
    assert row.cpic_level == "A" and row.cpic_pmids == "99999"
    assert row.latest_history_date == "2026-01-10"
    assert row.source_url == "https://www.clinpgx.org/clinicalAnnotation/900001"


def test_evidence_keeps_identifiers_and_pmids(live):
    e = pd.read_csv(live / "evidence.csv", dtype=str, keep_default_na=False)
    assert {"800001", "800002", "800003", "700001"} <= set(e.evidence_id)
    assert set(e[e.summary_annotation_id == "900001"].pmid) - {""} == {"11111", "22222", "33333"}


def test_coverage_counts_and_zero_fill(live):
    data = atlas.load_live(live)
    cov = atlas.coverage(data, "drugx", "GENEA", by_outcome=False)
    by = cov.set_index("population")
    # European: two PMIDs; one cohort of 1000 (not double counted), one with unknown size
    assert by.loc["European", "study_count"] == 2
    assert by.loc["European", "participants"] == 1000
    assert by.loc["European", "coverage"] == "Records present in loaded dataset"
    assert by.loc["European", "evidence_grade"] == "1A"
    # East Asian: one small study -> sparse
    assert by.loc["East Asian", "coverage"] == "Sparse in loaded dataset"
    # 'Unknown' is never zero-filled as if it were a population
    assert "Unknown" not in by.index
    # drugy only has Sub-Saharan African evidence -> other groups zero-filled
    cov_y = atlas.coverage(data, "drugy", by_outcome=False).set_index("population")
    assert cov_y.loc["European", "study_count"] == 0
    assert cov_y.loc["European", "coverage"] == "No records in loaded dataset"
    assert "ClinPGx release 2026-10-01" in cov_y.loc["European", "data_status"]


def test_attribution_text_has_required_elements(live):
    text = atlas.attribution_text(atlas.load_live(live)["manifest"])
    for needle in ["CC BY-NC-SA 4.0", "NON-COMMERCIAL", "SHARE-ALIKE", "Whirl-Carrillo", "CC0", "v9.9.9",
                   "Date accessed", "Changes made", "www.clinpgx.org", "Not for clinical use"]:
        assert needle in text, needle


def test_failed_ingest_keeps_previous_data(live, monkeypatch):
    before = (live / "manifest.json").read_text()

    def broken(url, accept="*/*", retries=3, data=None):
        raise RuntimeError("network down")
    monkeypatch.setattr(ingest, "_get", broken)
    with pytest.raises(RuntimeError):
        ingest.run(live, log=lambda *_: None, pubmed_cache=live.parent / "c.json")
    assert (live / "manifest.json").read_text() == before


def test_format_change_is_reported_clearly():
    bad = {"summary_annotations": pd.DataFrame({"summary_annotation_id": ["1"]}),
           "summary_ann_evidence": pd.DataFrame({"summary_annotation_id": ["1"]})}
    with pytest.raises(ValueError, match="ClinPGx may have changed"):
        ingest.parse_summary_annotations(bad)
