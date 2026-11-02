"""Verify a downloaded Atlas dataset against independent reference facts.

    python verify.py            # checks data/live, writes verification/REPORT.md

Checks
------
1. Ingest integrity: every source downloaded, release dates/versions recorded,
   row counts non-zero, joins working (evidence -> studies -> populations).
2. Licences: the licence text shipped inside the ClinPGx downloads is present, and
   the licence the app shows and puts in exports is the one that file names.
3. Reference gene-drug pairs (verification/expected.csv): CPIC level, CPIC guideline
   PMIDs and top ClinPGx level match values taken from CPIC's own repository and
   the guideline publications; dominant ancestry where the literature is clear.
4. Coverage of the location/ancestry fields, and a fixed random sample of studies
   to spot-check by hand against PubMed.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import atlas

HERE = Path(__file__).parent
EXPECTED = HERE / 'verification' / 'expected.csv'
REPORT = HERE / 'verification' / 'REPORT.md'


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, area, check, ok, detail=''):
        self.rows.append({'area': area, 'check': check, 'result': 'PASS' if ok else 'FAIL',
                          'detail': detail})
        return ok

    def warn(self, area, check, detail):
        self.rows.append({'area': area, 'check': check, 'result': 'NOTE', 'detail': detail})

    @property
    def failed(self):
        return [r for r in self.rows if r['result'] == 'FAIL']


def check_ingest(c: Checks, data: dict):
    m = data['manifest']
    src = m['sources']
    for key in ('summaryAnnotations', 'variantAnnotations'):
        s = src.get('clinpgx', {}).get(key, {})
        c.add('Ingest', f'ClinPGx {key} downloaded from api.clinpgx.org',
              s.get('url', '').startswith('https://api.clinpgx.org/') and s.get('bytes', 0) > 10000,
              f"{s.get('bytes', 0):,} bytes; release {s.get('release_date') or 'not stated'}; "
              f"sha256 {s.get('sha256', '')[:12]}…")
        c.add('Ingest', f'ClinPGx {key} release date recorded', bool(s.get('release_date')),
              s.get('release_date') or 'missing CREATED_ marker file')
    c.add('Ingest', 'CPIC pairs downloaded', src.get('cpic', {}).get('pairs', 0) > 100,
          f"{src.get('cpic', {}).get('pairs', 0):,} pairs; release {src.get('cpic', {}).get('release')}")
    c.add('Ingest', 'CPIC release number recorded', bool(src.get('cpic', {}).get('release')),
          str(src.get('cpic', {}).get('release')))
    pm = src.get('pubmed', {})
    c.add('Ingest', 'PubMed look-ups completed without error', 'error' not in pm and not pm.get('skipped'),
          f"{pm.get('pmids', 0):,} PMIDs; {pm.get('not_found', 0):,} not found"
          + (f"; error: {pm['error']}" if 'error' in pm else ''))
    for name in ('associations', 'evidence', 'study_populations', 'pubmed', 'study_locations',
                 'cpic_pairs'):
        c.add('Ingest', f'{name}.csv has rows', len(data[name]) > 0, f'{len(data[name]):,} rows')
    a, e = data['associations'], data['evidence']
    linked = e['summary_annotation_id'].isin(a['summary_annotation_id']).mean()
    c.add('Ingest', 'Evidence rows link to summary annotations', linked > 0.95,
          f'{linked:.1%} linked (the rest belong to annotations with no drug or gene listed)')
    var = e[e['evidence_type'].str.startswith('Variant')]
    with_sp = var['evidence_id'].isin(data['study_populations']['variant_annotation_id']).mean()
    c.add('Ingest', 'Variant evidence links to study parameters', with_sp > 0.5,
          f'{with_sp:.1%} of variant-annotation evidence has study parameters')
    with_pmid = (var['pmid'] != '').mean()
    c.add('Ingest', 'Variant evidence carries PMIDs', with_pmid > 0.9, f'{with_pmid:.1%}')
    dates = pd.to_datetime(a['latest_history_date'], errors='coerce')
    c.add('Ingest', 'Annotation dates parse and are not in the future',
          dates.notna().mean() > 0.95 and dates.max() <= pd.Timestamp.now() + pd.Timedelta(days=2),
          f'{dates.min():%Y-%m-%d} to {dates.max():%Y-%m-%d}')
    from ingest import BIOGEO_GROUPS, IN_VITRO
    labels = set(data['study_populations']['population'])
    c.add('Ingest', 'Every ancestry value is a recognised ClinPGx group',
          labels <= set(BIOGEO_GROUPS + [IN_VITRO]),
          'unexpected: ' + '; '.join(sorted(labels - set(BIOGEO_GROUPS + [IN_VITRO])))[:200]
          if not labels <= set(BIOGEO_GROUPS + [IN_VITRO]) else f'{len(labels)} labels, all recognised')
    groups = labels
    std = {'European', 'East Asian', 'Sub-Saharan African', 'Latino', 'Central/South Asian',
           'Near Eastern', 'Oceanian', 'American', 'African American/Afro-Caribbean'}
    c.add('Ingest', 'All 9 ClinPGx biogeographical groups present', std <= groups,
          'missing: ' + ', '.join(sorted(std - groups)) if not std <= groups else
          f'also present: {", ".join(sorted(groups - std)) or "none"}')


def check_licences(c: Checks, live_dir: Path):
    lic_dir = live_dir / 'upstream_licences'
    texts = {f.name: f.read_text('utf-8', errors='replace') for f in sorted(lic_dir.glob('*'))} \
        if lic_dir.exists() else {}
    c.add('Licences', 'Licence/readme files shipped inside ClinPGx downloads were saved', bool(texts),
          ', '.join(texts) or 'none found')
    from ingest import detect_licence
    found = detect_licence(texts)
    c.add('Licences', 'ClinPGx licence file names a Creative Commons licence', bool(found),
          found['name'] if found else 'none found — read upstream_licences/ by hand')
    shown = atlas.clinpgx_licence(atlas.with_detected_licence(
        json.loads((live_dir / 'manifest.json').read_text('utf-8')), live_dir))
    c.add('Licences', 'App and exports show the licence named in that file',
          bool(found) and shown['short'] == found['short'], f"app shows {shown.get('short')}")
    if found and found.get('noncommercial'):
        c.warn('Licences', 'NonCommercial restriction',
               'ClinPGx data may not be used for commercial purposes; the app footer, About tab '
               'and every export say so.')
    text = atlas.attribution_text(atlas.with_detected_licence(
        json.loads((live_dir / 'manifest.json').read_text('utf-8')), live_dir))
    c.add('Licences', 'Export attribution names the licence, NC and share-alike terms',
          bool(found) and found['short'] in text and 'SHARE-ALIKE' in text
          and ('NON-COMMERCIAL' in text) == bool(found.get('noncommercial')), '')
    for name, text in texts.items():
        first = ' '.join(text.split())[:300]
        c.warn('Licences', f'Excerpt of {name}', first + ('…' if len(text) > 300 else ''))
    m = json.loads((live_dir / 'manifest.json').read_text('utf-8'))
    for k in ('cpic', 'pubmed'):
        c.add('Licences', f'{k} licence recorded in manifest', k in m.get('licences', {}),
              m.get('licences', {}).get(k, {}).get('name', ''))
    ne = (HERE / 'data' / 'geo' / 'NATURAL_EARTH_LICENSE.md').read_text('utf-8').lower()
    c.add('Licences', 'Natural Earth map is public domain', 'public domain' in ne, 'bundled licence file')


def check_pairs(c: Checks, data: dict) -> pd.DataFrame:
    exp = pd.read_csv(EXPECTED, dtype=str, keep_default_na=False)
    out = []
    for _, r in exp.iterrows():
        label = f'{r.drug} / {r.gene}'
        cp = data['cpic_pairs']
        cp = cp[(cp.drug == r.drug) & (cp.gene == r.gene)]
        level = cp.cpic_level.iloc[0] if len(cp) else '(not listed)'
        pmids = set(cp.cpic_pmids.iloc[0].split(';')) - {''} if len(cp) else set()
        want = set(r.expected_guideline_pmids.split(';'))
        anns = atlas.annotations_for(data, r.drug, r.gene)
        top = atlas.best_level(anns.level_of_evidence) if len(anns) else '(none)'
        st = atlas.studies(data, r.drug, r.gene)
        anc = atlas.ancestry_coverage(st)
        groups = anc[~anc.ancestry.isin(['Multiple groups', 'Unknown', 'Not recorded'])]
        dom = groups.sort_values('studies', ascending=False).ancestry.iloc[0] if len(groups) else ''
        locs = atlas.country_coverage(st).query('studies > 0').nlargest(3, 'studies')
        c.add('Reference pairs', f'{label}: CPIC level = {r.expected_cpic_level}',
              level == r.expected_cpic_level, f'found {level}')
        c.add('Reference pairs', f'{label}: CPIC guideline PMIDs include {", ".join(sorted(want))}',
              want <= pmids, f'found {", ".join(sorted(pmids)) or "none"}')
        c.add('Reference pairs', f'{label}: top ClinPGx level = {r.expected_top_clinpgx_level}',
              top == r.expected_top_clinpgx_level, f'found {top} ({len(anns)} annotations)')
        if r.expected_dominant_ancestry:
            c.add('Reference pairs', f'{label}: most-studied ancestry = {r.expected_dominant_ancestry}',
                  dom == r.expected_dominant_ancestry, f'found {dom}')
        out.append({'pair': label, 'cpic_level': level, 'top_clinpgx_level': top,
                    'annotations': len(anns), 'studies': len(st),
                    'most_studied_ancestry': dom,
                    'top_study_countries': ', '.join(f'{x.country} ({x.studies})'
                                                     for x in locs.itertuples()),
                    'reference': r.reference})
    return pd.DataFrame(out)


def coverage_stats(c: Checks, data: dict) -> dict:
    st = atlas.studies(data)
    s = atlas.location_gaps_summary(st)
    n = s['studies'] or 1
    c.warn('Coverage', 'Studies with recorded ancestry', f"{s['with_ancestry']:,} of {s['studies']:,} "
           f"({s['with_ancestry'] / n:.0%})")
    c.warn('Coverage', 'Studies with a country-level study location (PubMed MeSH)',
           f"{s['with_study_location']:,} ({s['with_study_location'] / n:.0%}); "
           f"{s['not_yet_indexed']:,} not yet indexed; {s['region_only']:,} region only")
    c.warn('Coverage', 'Studies with a recognised research-team country',
           f"{s['with_team_location']:,} ({s['with_team_location'] / n:.0%})")
    if 'origin_terms' not in data['pubmed'].columns:
        c.add('Coverage', 'PubMed data separates “ethnology” tags from study location', False,
              'downloaded before v0.5: run python ingest.py again, then python verify.py')
    else:
        n_origin = (data['pubmed']['origin_terms'] != '').sum()
        c.add('Coverage', 'PubMed data separates “ethnology” tags from study location', True,
              f'{n_origin:,} studies carry origin-only place tags, kept out of study location')
    c.warn('Coverage', 'Study-location coverage is limited',
           'NLM adds geographic MeSH terms only when place is a subject of the paper, so most '
           'studies have no indexed country. The app reports this share on every view.')
    loc = st[st.study_countries != '']
    agree = loc.apply(lambda r: bool(set(r.study_countries.split(';'))
                                     & set(r.team_countries.split(';'))), axis=1).mean()
    c.add('Consistency', 'Indexed study country matches an author country in most studies',
          agree >= 0.7, f'{agree:.0%} of {len(loc):,} located studies')
    for name, isos, group in [
            ('Japan, China, Korea, Taiwan', {'JPN', 'CHN', 'KOR', 'TWN'}, 'East Asian'),
            ('Germany, France, Italy, Spain, Netherlands, UK, Sweden, Denmark, Poland',
             {'DEU', 'FRA', 'ITA', 'ESP', 'NLD', 'GBR', 'SWE', 'DNK', 'POL'}, 'European')]:
        sub = loc[loc.study_countries.str.split(';').map(lambda x: bool(set(x) & isos))]
        spec = sub.ancestry.str.split(';').map(lambda g: set(g) - atlas.NON_GROUP_LABELS
                                               - {'Not recorded'})
        spec = spec[spec.map(bool)]
        share = spec.map(lambda g: group in g).mean() if len(spec) else 0
        c.add('Consistency', f'Studies located in {name} mostly include {group} participants',
              share >= 0.8, f'{share:.0%} of {len(spec):,} studies naming a specific group')
    return s


def spot_sample(data: dict, k: int = 12, seed: int = 20261031) -> pd.DataFrame:
    st = atlas.studies(data)
    st = st[st.study_countries != '']
    rnd = random.Random(seed)
    pick = rnd.sample(sorted(st.pmid, key=int), min(k, len(st)))
    s = st.set_index('pmid').loc[pick].reset_index()
    pm = data['pubmed'].set_index('pmid')
    s['mesh_geo_terms'] = s.pmid.map(pm['geo_terms'])
    s['study_location'] = s.study_countries.map(
        lambda v: ', '.join(atlas.country_name(i) for i in v.split(';')))
    s['research_team'] = s.team_countries.map(
        lambda v: ', '.join(atlas.country_name(i) for i in v.split(';') if i))
    s['pubmed_url'] = s.pmid.map(lambda p: f'https://pubmed.ncbi.nlm.nih.gov/{p}/')
    return s[['pmid', 'year', 'ancestry', 'mesh_geo_terms', 'study_location', 'research_team',
              'pubmed_url']]


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    for _, r in df.iterrows():
        lines.append('| ' + ' | '.join(str(r[c]).replace('|', '/') for c in cols) + ' |')
    return '\n'.join(lines)


def main(live_dir: Path = atlas.LIVE_DIR) -> int:
    if not atlas.live_available(live_dir):
        print('No downloaded data found. Run: python ingest.py')
        return 2
    data = atlas.load_live(live_dir)
    c = Checks()
    check_ingest(c, data)
    check_licences(c, live_dir)
    pairs = check_pairs(c, data)
    coverage_stats(c, data)
    sample = spot_sample(data)

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    passed = sum(r['result'] == 'PASS' for r in c.rows)
    report = [
        '# Human Response Atlas — verification report', '',
        f'Generated {now} from `{live_dir}`. {atlas.release_label(data["manifest"])}; '
        f'downloaded {data["manifest"]["accessed_utc"]}.', '',
        f'**{passed} checks passed, {len(c.failed)} failed.**', '',
        '## Checks', '', md_table(pd.DataFrame(c.rows)), '',
        '## Reference gene–drug pairs', '', md_table(pairs), '',
        '## Manual spot-check sample', '',
        'Open each PubMed link and confirm that the MeSH geographic term and author '
        'affiliations match the study location and research team shown.', '',
        md_table(sample), '',
    ]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text('\n'.join(report), 'utf-8')
    pairs.to_csv(REPORT.with_name('reference_pairs.csv'), index=False)
    sample.to_csv(REPORT.with_name('spot_check_sample.csv'), index=False)
    for r in c.rows:
        print(f"[{r['result']}] {r['area']}: {r['check']} — {r['detail']}")
    print(f'\n{passed} passed, {len(c.failed)} failed. Report: {REPORT}')
    return 1 if c.failed else 0


if __name__ == '__main__':
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else atlas.LIVE_DIR))
