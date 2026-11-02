import pandas as pd
import pytest

import atlas
import geo
import ingest
from tests import fixtures


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "_get", fixtures.fake_get)
    out = tmp_path / "live"
    ingest.run(out, log=lambda *_: None, pubmed_cache=tmp_path / "pubmed.json")
    return atlas.load_live(out)


def test_ancestry_location_and_team_are_kept_apart(data):
    st = atlas.studies(data).set_index("pmid")
    # East Asian-ancestry cohort, indexed as studied in the USA, authors in Korea and USA
    assert st.loc["22222", "ancestry"] == "East Asian"
    assert st.loc["22222", "study_countries"] == "USA"
    assert st.loc["22222", "team_countries"] == "KOR;USA"
    anc = atlas.ancestry_coverage(atlas.studies(data)).set_index("ancestry")
    assert anc.loc["East Asian", "studied_in"] == "United States of America (1)"


def test_nothing_is_inferred(data):
    st = atlas.studies(data).set_index("pmid")
    # Not MeSH-indexed yet: no study location, even though the authors are in France
    # and the cohort is European.
    assert st.loc["33333", "study_countries"] == ""
    assert st.loc["33333", "team_countries"] == "FRA"
    assert "nationality" not in st.columns
    assert "nationality" in atlas.DIMENSIONS
    # Ancestry MeSH terms never become countries
    assert geo.mesh_to_country("Asian People") == (None, None)
    assert geo.mesh_to_country("European Continental Ancestry Group") == (None, None)
    # Region-level terms are kept as regions, not assigned to a country
    assert geo.mesh_to_country("Africa South of the Sahara")[0] is None


def test_country_coverage_lists_every_country(data):
    cov = atlas.country_coverage(atlas.studies(data))
    assert len(cov) == len(geo.country_table()) > 200
    by = cov.set_index("iso3")
    assert by.loc["DEU", "studies"] == 1 and by.loc["DEU", "participants"] == 1000
    assert by.loc["BRA", "status"] == "Missing"
    assert by.loc["USA", "ancestry_of_participants"] == "East Asian (1)"
    team = atlas.country_coverage(atlas.studies(data), "research team").set_index("iso3")
    assert team.loc["KOR", "studies"] == 1 and by.loc["KOR", "studies"] == 0


def test_ancestry_participants_are_group_specific(data):
    anc = atlas.ancestry_coverage(atlas.studies(data), all_groups=["Oceanian"]).set_index("ancestry")
    assert anc.loc["European", "studies"] == 2
    assert anc.loc["European", "participants"] == 1000      # one size unknown
    assert anc.loc["Oceanian", "status"] == "Missing"


def test_quality_indicators(data):
    st = atlas.studies(data).set_index("pmid")
    assert st.loc["22222", "design"] == "Randomised controlled trial"
    assert st.loc["11111", "design"] == "Observational"        # from ClinPGx study type
    assert atlas.study_design("Journal Article;Meta-Analysis") == "Meta-analysis / systematic review"
    ind = atlas.indicators(atlas.studies(data))
    assert ind["studies"] == 4 and ind["trials_or_meta"] == 1 and ind["latest_year"] == 2024
    assert ind["pct_significant"] == 67                          # 2 of 3 stated
    assert atlas.quality_signal(ind) == "Stronger"
    assert atlas.quality_signal(atlas.indicators(st.loc[["44444"]].reset_index())) == "Weaker"


def test_location_summary_and_attribution(data):
    s = atlas.location_gaps_summary(atlas.studies(data))
    assert s == {"studies": 4, "with_study_location": 3, "not_yet_indexed": 1,
                 "region_only": 0, "with_team_location": 4, "with_ancestry": 4}
    text = atlas.attribution_text(data["manifest"])
    assert "National Library of Medicine" in text and "Natural Earth" in text
    assert "never inferred" in text


@pytest.mark.parametrize("aff,iso", [
    ("Seoul National University, Seoul 03080, Republic of Korea.", "KOR"),
    ("Vanderbilt, Nashville, TN 37232, USA. a@b.edu", "USA"),
    ("Western University, London, Ontario, Canada", "CAN"),
    ("Tbilisi State University, Tbilisi, Georgia", None),
    ("Kyoto University, Kyoto, Japan. Electronic address: a@b.jp", "JPN"),
])
def test_affiliation_countries(aff, iso):
    assert geo.affiliation_country(aff) == iso


def test_pubmed_parse_handles_unindexed():
    recs = __import__("pubmed").parse_efetch(fixtures.pubmed_xml(["33333", "44444"]))
    assert recs["33333"]["mesh_indexed"] is False
    assert recs["44444"]["study_countries"] == ["NGA"]
    assert recs["44444"]["regions"] == ["Africa South of the Sahara"]
    assert pd.Series(recs["44444"]["affiliation_countries"]).tolist() == ["GBR", "NGA"]


def test_pubmed_outage_is_not_fatal(tmp_path, monkeypatch):
    def no_pubmed(url, accept="*/*", retries=3, data=None):
        if "efetch" in url:
            raise RuntimeError("PubMed unavailable")
        return fixtures.fake_get(url, accept, retries, data)
    monkeypatch.setattr(ingest, "_get", no_pubmed)
    m = ingest.run(tmp_path / "live", log=lambda *_: None, pubmed_cache=tmp_path / "p.json")
    assert "PubMed unavailable" in m["sources"]["pubmed"]["error"]
    data = atlas.load_live(tmp_path / "live")
    assert atlas.country_coverage(atlas.studies(data))["studies"].sum() == 0


def test_empty_selection_does_not_break(data):
    st = atlas.studies(data, "no-such-medicine")
    assert len(st) == 0
    assert "ancestry" in atlas.ancestry_coverage(st).columns
    assert atlas.country_coverage(st)["studies"].sum() == 0


@pytest.mark.parametrize("raw,groups", [
    ("European", ["European"]),
    ("Multiple groups, 87.8% white, 7% black, 2.7% hispanic", ["Multiple groups"]),
    ('"Multiple groups, ""Southern United States"""', ["Multiple groups"]),
    ("East Asian;European", ["East Asian", "European"]),
    ("unknown", ["Unknown"]),
    ("Custom, in vitro", ["In vitro (no participants)"]),
    ("Participants self-identified as of African ancestry", ["Unknown"]),
])
def test_population_descriptions_are_not_groups(raw, groups):
    assert ingest.clean_population(raw) == groups


def test_free_text_population_is_cleaned(data):
    sp = data["study_populations"]
    assert set(sp["population"]) <= set(ingest.BIOGEO_GROUPS + [ingest.IN_VITRO])
    assert "87.8% Yoruba" in " ".join(sp["population_detail"])


def test_old_downloads_are_repaired_on_load():
    old = pd.DataFrame({"study_parameters_id": ["1"] * 3, "summary_annotation_id": ["9"] * 3,
                        "pmid": ["5"] * 3,
                        "population": ["Multiple groups", "87.8% white", "7% black"]})
    fixed = atlas.clean_study_populations(old)
    assert fixed["population"].tolist() == ["Multiple groups"]


def test_licence_is_read_from_the_download():
    lic = ingest.detect_licence({"LICENSE.txt": fixtures.LICENSE_TEXT})
    assert lic["short"] == "CC BY-NC-SA 4.0" and lic["noncommercial"] and lic["sharealike"]
    old_manifest = {"licences": {"clinpgx": {"short": "CC BY-SA 4.0"}}}
    assert ingest.detect_licence({}) is None
    assert atlas.clinpgx_licence(old_manifest)["short"] == "CC BY-SA 4.0"


def test_ethnology_headings_are_origin_not_location(data):
    # PMID 22222 is indexed "Korea/ethnology" (participants' origin) and "California"
    st = atlas.studies(data).set_index("pmid")
    assert st.loc["22222", "study_countries"] == "USA"
    pm = data["pubmed"].set_index("pmid")
    assert pm.loc["22222", "origin_terms"] == "Korea/ethnology"


def test_old_cache_records_are_refetched():
    import pubmed
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    old = {"fetched_utc": now.isoformat(), "mesh_indexed": True}
    assert pubmed._needs_fetch(old, now) is True
    assert pubmed._needs_fetch({**old, "schema": pubmed.SCHEMA}, now) is False


def test_cpic_release_falls_back_to_github(tmp_path, monkeypatch):
    import json as _json

    def no_changelog(url, accept="*/*", retries=3, data=None):
        if "/change_log" in url:
            return b"[]"
        if "api.github.com" in url:
            return _json.dumps({"tag_name": "v1.62.0"}).encode()
        return fixtures.fake_get(url, accept, retries, data)
    monkeypatch.setattr(ingest, "_get", no_changelog)
    m = ingest.run(tmp_path / "live", log=lambda *_: None, pubmed_cache=tmp_path / "p.json")
    assert m["sources"]["cpic"]["release"] == "v1.62.0"


def test_unreadable_old_licence_falls_back_to_noncommercial(tmp_path):
    (tmp_path / "upstream_licences").mkdir()
    (tmp_path / "upstream_licences" / "x.txt").write_text("no licence named here")
    old = {"licences": {"clinpgx": {"name": "Creative Commons Attribution-ShareAlike 4.0"}}}
    lic = atlas.clinpgx_licence(atlas.with_detected_licence(old, tmp_path))
    assert lic["short"] == "CC BY-NC-SA 4.0"
