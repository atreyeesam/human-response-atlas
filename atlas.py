"""Evidence coverage logic for the Human Response Atlas.

Coverage labels describe the *loaded dataset* only. "No records in loaded
dataset" means the loaded ClinPGx snapshot has no annotated study for that
population - NOT that the scientific literature contains none.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ingest import LEVEL_ORDER, best_level

REQUIRED_COLUMNS = {'record_id', 'drug', 'gene', 'outcome', 'population',
                    'study_count', 'participants', 'evidence_grade', 'source_url', 'data_status'}

LIVE_DIR = Path(__file__).parent / 'data' / 'live'
DEMO_FILE = Path(__file__).parent / 'data' / 'demo_evidence.csv'

# Populations that are not a single biogeographical group are reported but
# never zero-filled, so they cannot create artificial "gaps".
NON_GROUP_LABELS = {'Unknown', 'Multiple groups', '', 'In vitro (no participants)'}

SPARSE_MIN_STUDIES = 2
SPARSE_MIN_PARTICIPANTS = 200


def validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')
    if (df[['study_count', 'participants']] < 0).any().any():
        raise ValueError('Counts cannot be negative')
    return df


def classify(study_count, participants) -> str:
    if study_count == 0:
        return 'No records in loaded dataset'
    if study_count < SPARSE_MIN_STUDIES:
        return 'Sparse in loaded dataset'
    if pd.notna(participants) and participants < SPARSE_MIN_PARTICIPANTS:
        return 'Sparse in loaded dataset'
    return 'Records present in loaded dataset'


def gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Return *dataset coverage labels*, NOT clinical evidence conclusions."""
    df = validate(df).copy()
    df['coverage'] = [classify(s, p) for s, p in zip(df['study_count'], df['participants'])]
    return df


# --------------------------------------------------------------------------- #
# Live ClinPGx + CPIC data
# --------------------------------------------------------------------------- #
def live_available(live_dir: Path = LIVE_DIR) -> bool:
    return (live_dir / 'manifest.json').exists()


def load_live(live_dir: Path = LIVE_DIR) -> dict:
    def read(n):
        f = live_dir / n
        return pd.read_csv(f, dtype=str, keep_default_na=False) if f.exists() else pd.DataFrame()
    data = {
        'pubmed': read('pubmed.csv'),
        'study_locations': read('study_locations.csv'),
        'manifest': json.loads((live_dir / 'manifest.json').read_text('utf-8')),
        'associations': read('associations.csv'),
        'evidence': read('evidence.csv'),
        'study_populations': read('study_populations.csv'),
        'cpic_pairs': read('cpic_pairs.csv'),
        'cpic_publications': read('cpic_publications.csv'),
    }
    data['manifest'] = with_detected_licence(data['manifest'], live_dir)
    sp = clean_study_populations(data['study_populations'])
    for c in ('study_cases', 'study_controls'):
        sp[c] = pd.to_numeric(sp[c], errors='coerce')
    data['study_populations'] = sp
    return data


def with_detected_licence(manifest: dict, live_dir: Path) -> dict:
    """Use the licence named in ClinPGx's own LICENSE.txt (fixes pre-v0.5 manifests)."""
    from ingest import LICENCES, detect_licence
    lic_dir = live_dir / 'upstream_licences'
    texts = {f.name: f.read_text('utf-8', errors='replace') for f in sorted(lic_dir.glob('*'))} \
        if lic_dir.exists() else {}
    found = detect_licence(texts)
    licences = {**LICENCES, **manifest.get('licences', {})}
    if found:
        licences['clinpgx'] = found
    elif 'short' not in licences.get('clinpgx', {}):
        # unreadable licence from an old download: fall back to the stricter, known licence
        licences['clinpgx'] = LICENCES['clinpgx']
    return {**manifest, 'licences': licences}


def clinpgx_licence(manifest: dict | None) -> dict:
    from ingest import LICENCES
    return (manifest or {}).get('licences', {}).get('clinpgx', LICENCES['clinpgx'])


def clean_study_populations(sp: pd.DataFrame) -> pd.DataFrame:
    """Repair downloads made before v0.5, where descriptive text after a group name
    (e.g. 'Multiple groups, 87.8% white') was split into fake population labels."""
    from ingest import BIOGEO_GROUPS, IN_VITRO, clean_population
    if sp.empty or sp['population'].isin(BIOGEO_GROUPS + [IN_VITRO]).all():
        return sp
    key = 'study_parameters_id'
    raw = sp.groupby(key)['population'].agg(lambda x: ', '.join(dict.fromkeys(x)))
    fixed = raw.map(clean_population)
    base = sp.drop(columns=['population']).drop_duplicates(
        subset=[c for c in sp.columns if c != 'population'])
    base = base.assign(population=base[key].map(fixed)).explode('population')
    if 'population_detail' not in base:
        base['population_detail'] = base[key].map(raw)
    return base.reset_index(drop=True)


def release_label(manifest: dict) -> str:
    c = manifest['sources'].get('clinpgx', {})
    dates = sorted({v.get('release_date') for v in c.values() if v.get('release_date')})
    cpic = manifest['sources'].get('cpic', {}).get('release')
    parts = [f"ClinPGx release {', '.join(dates) or 'date not stated'}"]
    parts.append(f"CPIC {cpic}" if cpic else 'CPIC release not stated')
    return ' · '.join(parts)


def _participants_per_study(group: pd.DataFrame) -> float:
    """Approximate cohort size: largest cases+controls reported per PMID, summed.

    The same cohort is often annotated for several variants, so summing every
    study-parameter row would double count. Returns NaN when no size is reported.
    """
    size = group['study_cases'].fillna(0) + group['study_controls'].fillna(0)
    size = size.where(group['study_cases'].notna() | group['study_controls'].notna())
    per_pmid = size.groupby(group['pmid']).max()
    return float(per_pmid.sum()) if per_pmid.notna().any() else float('nan')


def coverage(data: dict, drug: str, gene: str | None = None,
             by_outcome: bool = True) -> pd.DataFrame:
    """Drug-gene(-outcome) x population coverage table in the Atlas schema.

    Every biogeographical group observed anywhere in the loaded snapshot is
    listed for each drug-gene(-outcome), so groups with no linked studies show
    as explicit zero rows instead of disappearing.
    """
    assoc = data['associations']
    assoc = assoc[assoc['drug'] == drug]
    if gene:
        assoc = assoc[assoc['gene'] == gene]
    keys = ['drug', 'gene'] + (['outcome'] if by_outcome else [])
    sp = data['study_populations'].merge(
        assoc[['summary_annotation_id', 'drug', 'gene', 'outcome', 'level_of_evidence',
               'latest_history_date', 'source_url']],
        on='summary_annotation_id', how='inner')

    rows = []
    for key, grp in sp.groupby(keys + ['population'], sort=True):
        rec = dict(zip(keys + ['population'], key))
        rec.update({
            'study_count': grp['pmid'].replace('', pd.NA).dropna().nunique(),
            'participants': _participants_per_study(grp),
            'evidence_grade': best_level(grp['level_of_evidence']),
            'record_id': ';'.join(sorted(grp['summary_annotation_id'].unique())),
            'pmids': ';'.join(sorted(grp['pmid'].replace('', pd.NA).dropna().unique())),
            'source_url': grp.sort_values('level_of_evidence', key=lambda s: s.map(
                {lv: i for i, lv in enumerate(LEVEL_ORDER)}).fillna(99))['source_url'].iloc[0],
            'source_date': grp['latest_history_date'].max(),
        })
        rows.append(rec)
    cols = keys + ['population', 'study_count', 'participants', 'evidence_grade',
                   'record_id', 'pmids', 'source_url', 'source_date']
    found = pd.DataFrame(rows, columns=cols)

    # Zero-fill: every observed single biogeographical group, for every combo.
    groups = sorted(set(data['study_populations']['population']) - NON_GROUP_LABELS)
    combos = assoc[keys].drop_duplicates()
    if combos.empty:
        extra = [] if by_outcome else ['outcome']
        return pd.DataFrame(columns=cols + extra + ['data_status', 'coverage'])
    grid = combos.merge(pd.DataFrame({'population': groups}), how='cross')
    table = grid.merge(found, on=keys + ['population'], how='outer')
    table['study_count'] = table['study_count'].fillna(0).astype(int)
    table.loc[table['study_count'] == 0, 'participants'] = 0
    for c in ('evidence_grade', 'record_id', 'pmids', 'source_url', 'source_date'):
        table[c] = table[c].fillna('')
    if not by_outcome:
        table['outcome'] = 'All outcomes'
    table['data_status'] = release_label(data['manifest'])
    return gaps(table.sort_values(keys + ['study_count'], ascending=[True] * len(keys) + [False])
                .reset_index(drop=True))


def cpic_for(data: dict, drug: str, gene: str | None = None) -> pd.DataFrame:
    p = data['cpic_pairs']
    p = p[p['drug'] == drug]
    return p[p['gene'] == gene] if gene else p


def annotations_for(data: dict, drug: str, gene: str | None = None) -> pd.DataFrame:
    a = data['associations']
    a = a[a['drug'] == drug]
    if gene:
        a = a[a['gene'] == gene]
    order = {lv: i for i, lv in enumerate(LEVEL_ORDER)}
    return a.sort_values('level_of_evidence', key=lambda s: s.map(order).fillna(99))


def attribution_text(manifest: dict) -> str:
    """Attribution block that must travel with any export (ClinPGx licence + CPIC requests)."""
    accessed = manifest.get('accessed_utc', '')[:10]
    lic = clinpgx_licence(manifest)
    nc = lic.get('noncommercial', 'NC' in lic.get('short', ''))
    c = manifest['sources'].get('clinpgx', {})
    cp = manifest['sources'].get('cpic', {})
    lines = [
        'HUMAN RESPONSE ATLAS - DATA ATTRIBUTION AND LICENCE',
        '',
        'This export contains data derived from ClinPGx (https://www.clinpgx.org), comprising',
        'PharmGKB(R) and CPIC(R) content.',
        '',
        'ClinPGx / PharmGKB data',
        f"  Downloaded from: {', '.join(v['url'] for v in c.values())}",
        f"  Release date(s): {', '.join(sorted({v.get('release_date') or 'not stated' for v in c.values()}))}",
        f'  Date accessed: {accessed}',
        f"  Licence: {lic['name']}",
        f"           {lic['url']}",
        f"           (as stated in {lic.get('detected_from', 'the ClinPGx download')})",
        '  Data usage policy: https://www.clinpgx.org/page/dataUsagePolicy',
        f"  How to cite ClinPGx: {lic.get('cite', 'https://www.clinpgx.org/page/citingClinpgx')}",
        '  Please cite: Whirl-Carrillo M, Huddart R, Gong L, et al. An evidence-based framework',
        '  for evaluating pharmacogenomics knowledge for personalized medicine.',
        '  Clin Pharmacol Ther. 2021;110(3):563-572. doi:10.1002/cpt.2350',
        '  Changes made: rows were filtered, joined to study parameters, and aggregated by',
        '  biogeographical group (distinct PMIDs; approximate cohort sizes) by Human Response Atlas.',
        *(['  NON-COMMERCIAL: this data may not be used for commercial purposes, and ClinPGx data',
            '  may never be sold for private or commercial use.'] if nc else []),
        '  SHARE-ALIKE: if you distribute this file or anything derived from it, every recipient',
        f"  must first agree to be bound by {lic.get('short', 'the same licence')}, and proof of that",
        '  agreement must be available to ClinPGx (per the LICENSE.txt shipped with the data).',
        '',
        'CPIC data',
        f"  Source: {cp.get('endpoints', {}).get('pair_view', 'CPIC API')}",
        f"  CPIC data release: {cp.get('release') or 'not stated'}; date accessed: {accessed}",
        '  Licence: CC0 1.0. The primary source is www.clinpgx.org. CPIC guidelines and content',
        '  are subject to updates and modifications; refer to https://www.clinpgx.org/cpic to',
        '  confirm you are using the most current content. Cite the relevant CPIC guideline',
        '  publication(s) when a specific gene-drug pair is used.',
        '  CPIC(R) is a registered service mark of the U.S. Department of Health & Human Services.',
        '',
        'PubMed / MEDLINE (study location, research-team location, year, publication type)',
        '  Bibliographic data and MeSH indexing courtesy of the U.S. National Library of Medicine,',
        '  retrieved through NCBI E-utilities (https://eutils.ncbi.nlm.nih.gov/).',
        '  NLM terms: https://www.nlm.nih.gov/databases/download/terms_and_conditions.html',
        '  NLM does not endorse or verify this product.',
        '  Study location = MeSH geographic headings; research team = parsed author affiliations.',
        '',
        'Country boundaries: Natural Earth (public domain), https://www.naturalearthdata.com',
        '',
        'IMPORTANT',
        '  Ancestry (ClinPGx biogeographical group), study location and research-team location are',
        '  separate fields from separate sources; none is inferred from another. Nationality is not',
        '  recorded in these sources and is never inferred.',
        '  Coverage figures describe the loaded ClinPGx snapshot only. A zero means no annotated',
        '  study in this snapshot, not that no research exists. Not for clinical use, prescribing',
        '  or individual patient decisions. No endorsement by ClinPGx, PharmGKB or CPIC is implied.',
    ]
    return '\n'.join(lines)


# --------------------------------------------------------------------------- #
# v0.3 - global coverage: study location, research team, ancestry kept apart
# --------------------------------------------------------------------------- #
DIMENSIONS = {
    'study location': (
        'Where the study was carried out (or the place it concerns), from the geographic '
        'terms PubMed indexers add to each paper (MeSH). Place terms marked “ethnology” '
        'describe where participants’ families come from, so they are left out. Only about '
        '1 in 5 papers has a country tag, so the map shows where research was done at least. '
        'Says nothing about participants’ ancestry or nationality.'),
    'research team': (
        'Where the authors’ institutions are, parsed from PubMed author affiliations. '
        'A study can be led from one country and run in another.'),
    'ancestry': (
        'The biogeographical group of the participants, as curated by ClinPGx from each paper. '
        'This is genetic-ancestry-related, not geography: an East Asian-ancestry cohort can be '
        'recruited in the USA.'),
    'nationality': (
        'Not recorded by ClinPGx or PubMed. The Atlas never infers it from ancestry or location.'),
}
HIGH_LEVELS = {'1A', '1B', '2A', '2B'}
DESIGN_ORDER = ['Meta-analysis / systematic review', 'Randomised controlled trial',
                'Other clinical trial', 'Observational', 'Case report / series',
                'Other / not classified']


def study_design(pub_types: str, clinpgx_types: str = '') -> str:
    """Highest-ranked design from PubMed publication types, then ClinPGx study type."""
    pt = {t.strip().lower() for t in (pub_types or '').split(';')}
    if pt & {'meta-analysis', 'systematic review'}:
        return DESIGN_ORDER[0]
    if 'randomized controlled trial' in pt:
        return DESIGN_ORDER[1]
    if any(t.startswith('clinical trial') or t in {'controlled clinical trial', 'pragmatic clinical trial',
                                                    'equivalence trial'} for t in pt):
        return DESIGN_ORDER[2]
    if 'observational study' in pt or 'twin study' in pt:
        return DESIGN_ORDER[3]
    if 'case reports' in pt:
        return DESIGN_ORDER[4]
    ct = (clinpgx_types or '').lower()
    if 'meta' in ct:
        return DESIGN_ORDER[0]
    if 'clinical trial' in ct:
        return DESIGN_ORDER[2]
    if any(k in ct for k in ('cohort', 'case/control', 'case control', 'cross sectional', 'gwas',
                             'linkage', 'trios')):
        return DESIGN_ORDER[3]
    if 'case series' in ct or 'case report' in ct:
        return DESIGN_ORDER[4]
    return DESIGN_ORDER[5]


def studies(data: dict, drug: str | None = None, gene: str | None = None) -> pd.DataFrame:
    """One row per study (PMID) behind the ClinPGx variant annotations in scope.

    Ancestry, study location and research-team location are separate columns
    taken from separate sources; none is derived from another.
    """
    assoc = data['associations']
    if drug:
        assoc = assoc[assoc['drug'] == drug]
    if gene:
        assoc = assoc[assoc['gene'] == gene]
    ev = data['evidence']
    ev = ev[ev['summary_annotation_id'].isin(assoc['summary_annotation_id'])
            & ev['evidence_type'].str.startswith('Variant') & (ev['pmid'] != '')]
    lv_order = {lv: i for i, lv in enumerate(LEVEL_ORDER)}
    lv = assoc.drop_duplicates('summary_annotation_id').set_index(
        'summary_annotation_id')['level_of_evidence']
    ev = ev.assign(level=ev['summary_annotation_id'].map(lv).fillna(''))

    base = ev.groupby('pmid').agg(
        best_level=('level', lambda x: min(x, key=lambda v: lv_order.get(v, 99))),
        annotations=('summary_annotation_id', lambda x: ';'.join(sorted(set(x)))),
    ).reset_index()

    sp = data['study_populations']
    sp = sp[sp['summary_annotation_id'].isin(assoc['summary_annotation_id'])]
    if len(sp):
        size = (sp['study_cases'].fillna(0) + sp['study_controls'].fillna(0)).where(
            sp['study_cases'].notna() | sp['study_controls'].notna())
        sp = sp.assign(size=size)
        per_group = sp.groupby(['pmid', 'population'])['size'].max().reset_index()
        anc = per_group.groupby('pmid').agg(
            ancestry=('population', lambda x: ';'.join(sorted(set(x)))),
            participants=('size', lambda x: x.sum() if x.notna().any() else float('nan')))
        anc['participants_by_group'] = per_group.groupby('pmid').apply(
            lambda g: ';'.join(f"{p}={'' if pd.isna(v) else int(v)}"
                               for p, v in zip(g['population'], g['size'])),
            include_groups=False)
        sig = sp.groupby('pmid')['significance'].agg(
            lambda x: 'yes' if (x == 'yes').any() else ('no' if (x == 'no').any() else ''))
        ctype = sp.groupby('pmid')['study_type'].agg(lambda x: ';'.join(sorted(set(x) - {''})))
        base = base.merge(anc, on='pmid', how='left').merge(
            sig.rename('significant'), on='pmid', how='left').merge(
            ctype.rename('clinpgx_study_type'), on='pmid', how='left')
    for c in ('ancestry', 'significant', 'clinpgx_study_type', 'participants_by_group'):
        if c not in base:
            base[c] = ''
        base[c] = base[c].fillna('')
    if 'participants' not in base:
        base['participants'] = float('nan')
    base.loc[base['ancestry'] == '', 'ancestry'] = 'Not recorded'

    pm = data.get('pubmed', pd.DataFrame())
    if len(pm):
        base = base.merge(pm[['pmid', 'year', 'title', 'journal', 'pub_types', 'mesh_indexed',
                              'regions']], on='pmid', how='left')
    for c in ('year', 'title', 'journal', 'pub_types', 'mesh_indexed', 'regions'):
        if c not in base:
            base[c] = ''
        base[c] = base[c].fillna('')
    base['year'] = pd.to_numeric(base['year'], errors='coerce')
    base['design'] = [study_design(a, b) for a, b in zip(base['pub_types'],
                                                          base['clinpgx_study_type'])]

    loc = data.get('study_locations', pd.DataFrame())
    for basis, col in (('study location', 'study_countries'), ('research team', 'team_countries')):
        if len(loc):
            m = loc[loc['basis'] == basis].groupby('pmid')['iso3'].agg(
                lambda x: ';'.join(sorted(set(x))))
            base[col] = base['pmid'].map(m).fillna('')
        else:
            base[col] = ''
    return base


def country_name(iso3: str) -> str:
    import geo
    return geo.country_table().get(iso3, {}).get('name', iso3)


def _explode(df: pd.DataFrame, col: str) -> pd.DataFrame:
    out = df.assign(**{col: df[col].str.split(';')}).explode(col)
    return out[out[col] != '']


def indicators(group: pd.DataFrame) -> dict:
    """Evidence-quality indicators for a set of studies (shown side by side, not merged)."""
    n = group['pmid'].nunique()
    one = group.drop_duplicates('pmid')
    known = one['participants'].dropna()
    sig_stated = one[one['significant'].isin(['yes', 'no'])]
    designs = one['design'].value_counts()
    return {
        'studies': n,
        'participants': float(known.sum()) if len(known) else float('nan'),
        'best_level': best_level(one['best_level']),
        'studies_high_level': int(one['best_level'].isin(HIGH_LEVELS).sum()),
        'trials_or_meta': int(designs.reindex(DESIGN_ORDER[:3]).fillna(0).sum()),
        'observational': int(designs.get(DESIGN_ORDER[3], 0)),
        'other_design': int(designs.reindex(DESIGN_ORDER[4:]).fillna(0).sum()),
        'latest_year': int(one['year'].max()) if one['year'].notna().any() else None,
        'median_year': int(one['year'].median()) if one['year'].notna().any() else None,
        'pct_significant': (round(100 * (sig_stated['significant'] == 'yes').mean())
                            if len(sig_stated) else None),
    }


def quality_signal(ind: dict) -> str:
    """Transparent rule, documented in the app; not a validated score."""
    if not ind['studies']:
        return ''
    strong_design = ind['trials_or_meta'] > 0
    big = pd.notna(ind['participants']) and ind['participants'] >= 1000
    if ind['studies_high_level'] and (strong_design or big) and ind['studies'] >= 3:
        return 'Stronger'
    if ind['studies_high_level'] or big or ind['studies'] >= 3:
        return 'Moderate'
    return 'Weaker'


def _status(ind: dict, min_studies: int, min_participants: int) -> str:
    if ind['studies'] == 0:
        return 'Missing'
    if ind['studies'] < min_studies:
        return 'Limited'
    if pd.notna(ind['participants']) and ind['participants'] < min_participants:
        return 'Limited'
    return 'Available'


def country_coverage(st: pd.DataFrame, basis: str = 'study location',
                     min_studies: int = SPARSE_MIN_STUDIES,
                     min_participants: int = SPARSE_MIN_PARTICIPANTS) -> pd.DataFrame:
    """Every country on the map, with status and quality indicators for one basis."""
    import geo
    col = 'study_countries' if basis == 'study location' else 'team_countries'
    ex = _explode(st, col)
    rows = []
    for iso, meta in geo.country_table().items():
        grp = ex[ex[col] == iso]
        ind = indicators(grp)
        anc = (_explode(grp.drop_duplicates('pmid'), 'ancestry')['ancestry']
               .value_counts() if len(grp) else pd.Series(dtype=int))
        rows.append({'iso3': iso, 'country': meta['name'], 'region': meta['subregion'],
                     **ind, 'quality_signal': quality_signal(ind),
                     'status': _status(ind, min_studies, min_participants),
                     'ancestry_of_participants': ', '.join(f'{k} ({v})' for k, v in anc.items()),
                     'pmids': ';'.join(sorted(grp['pmid'].unique(), key=int))})
    return pd.DataFrame(rows)


def ancestry_coverage(st: pd.DataFrame, min_studies: int = SPARSE_MIN_STUDIES,
                      min_participants: int = SPARSE_MIN_PARTICIPANTS,
                      all_groups: list[str] | None = None) -> pd.DataFrame:
    ex = _explode(st, 'ancestry')
    # use the cohort size recorded for *this* group, not the whole multi-group study
    def group_size(row):
        for part in row['participants_by_group'].split(';'):
            name, _, val = part.partition('=')
            if name == row['ancestry']:
                return float(val) if val else float('nan')
        return float('nan')
    if len(ex):
        ex = ex.assign(participants=ex.apply(group_size, axis=1))
    groups = sorted(set(all_groups or []) | set(ex['ancestry']))
    rows = []
    for g in groups:
        grp = ex[ex['ancestry'] == g]
        ind = indicators(grp)
        status = ('Not a population group' if g in NON_GROUP_LABELS | {'Not recorded'}
                  else _status(ind, min_studies, min_participants))
        locs = _explode(grp.drop_duplicates('pmid'), 'study_countries')['study_countries'].map(
            country_name)
        rows.append({'ancestry': g, **ind, 'quality_signal': quality_signal(ind),
                     'status': status,
                     'studied_in': ', '.join(f'{k} ({v})' for k, v in
                                             locs.value_counts().head(8).items())})
    cols = ['ancestry', *indicators(ex.iloc[0:0]).keys(), 'quality_signal', 'status', 'studied_in']
    return pd.DataFrame(rows, columns=cols)


def ancestry_by_location(st: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Distinct studies per (ancestry group, study-location country)."""
    ex = _explode(st, 'ancestry')
    ex = ex.assign(study_countries=ex['study_countries'].replace('', 'Not indexed'))
    ex = _explode(ex, 'study_countries')
    ex = ex.assign(study_countries=ex['study_countries'].map(country_name))
    m = ex.groupby(['ancestry', 'study_countries'])['pmid'].nunique().reset_index(name='studies')
    keep = (m.groupby('study_countries')['studies'].sum().sort_values(ascending=False)
            .head(top).index)
    m.loc[~m['study_countries'].isin(keep), 'study_countries'] = 'Other countries'
    return m.groupby(['ancestry', 'study_countries'], as_index=False)['studies'].sum()


def location_gaps_summary(st: pd.DataFrame) -> dict:
    n = st['pmid'].nunique()
    return {
        'studies': n,
        'with_study_location': int((st['study_countries'] != '').sum()),
        'not_yet_indexed': int((st['mesh_indexed'].astype(str) == 'False').sum()),
        'region_only': int(((st['study_countries'] == '') & (st['regions'] != '')).sum()),
        'with_team_location': int((st['team_countries'] != '').sum()),
        'with_ancestry': int(st['ancestry'].str.split(';').map(
            lambda g: bool(set(g) - NON_GROUP_LABELS - {'Not recorded'})).sum()),
    }
