"""ClinPGx and CPIC, read from the local download made by ingest.py."""
from __future__ import annotations

from pathlib import Path

from ..models import NOT_SEARCHED, OK, Licence, Record, SourceResult

LICENCE = Licence('Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0)',
                  'https://creativecommons.org/licenses/by-nc-sa/4.0/',
                  'As stated in the LICENSE.txt shipped with the ClinPGx download. Non-commercial use only.')
CPIC_LICENCE = Licence('CC0 1.0 with CPIC attribution requests', 'https://creativecommons.org/publicdomain/zero/1.0/')


def _load(live_dir: Path | None):
    import atlas
    live_dir = Path(live_dir) if live_dir else atlas.LIVE_DIR
    return atlas.load_live(live_dir) if atlas.live_available(live_dir) else None


def search(names: list[str], live_dir: Path | None = None, data=None):
    """Return (clinpgx_result, cpic_result, curated ancestry {pmid: [groups]}, cpic rows)."""
    data = data if data is not None else _load(live_dir)
    if data is None:
        msg = 'no local ClinPGx download (run python ingest.py)'
        return (SourceResult('clinpgx', NOT_SEARCHED, error=msg, licence=LICENCE),
                SourceResult('cpic', NOT_SEARCHED, error=msg, licence=CPIC_LICENCE), {}, [])
    import atlas
    rel = atlas.release_label(data['manifest'])
    drugs = [n for n in names if n in set(data['associations'].drug)]
    st = atlas.studies(data, drugs[0]) if drugs else atlas.studies(data, '\x00none')
    for d in drugs[1:]:
        import pandas as pd
        st = pd.concat([st, atlas.studies(data, d)]).drop_duplicates('pmid')
    res = SourceResult('clinpgx', OK, licence=LICENCE,
                       queries=[{'category': 'pgx', 'query': f'local ClinPGx annotations for {", ".join(drugs) or names[0]} ({rel})',
                                 'total': len(st), 'retrieved': len(st)}])
    ancestry = {}
    loc = data.get('study_locations')
    places = {}
    if loc is not None and len(loc):
        for row in loc.itertuples():
            key = 'mesh_places' if row.basis == 'study location' else 'affiliation_countries'
            places.setdefault(row.pmid, {'mesh_places': [], 'affiliation_countries': []})[key].append(row.iso3)
    for r in st.itertuples():
        groups = [g for g in r.ancestry.split(';') if g and g not in ('Not recorded',)]
        ancestry[r.pmid] = groups
        res.records.append(Record(
            source='clinpgx', source_id=r.pmid, url=f'https://pubmed.ncbi.nlm.nih.gov/{r.pmid}/',
            kind='publication', title=r.title, year=int(r.year) if r.year == r.year else None,
            pmid=r.pmid, categories=['pgx'], publication_types=[t for t in r.pub_types.split(';') if t],
            extra={**places.get(r.pmid, {}),
                   'clinpgx_best_level': r.best_level, 'clinpgx_annotations': r.annotations,
                   'clinpgx_participants': None if r.participants != r.participants else int(r.participants)}))
    cp = data['cpic_pairs']
    cp = cp[cp.drug.isin(drugs)] if drugs else cp.iloc[0:0]
    cpic = SourceResult('cpic', OK, licence=CPIC_LICENCE,
                        queries=[{'category': 'guideline', 'query': 'local CPIC gene-drug pairs',
                                  'total': len(cp), 'retrieved': len(cp)}])
    return res, cpic, ancestry, cp.to_dict('records')
