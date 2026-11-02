"""Europe PMC: publications, preprints and open-access full text availability."""
from __future__ import annotations

from .. import queries
from ..http import SourceError
from ..models import FAILED, OK, Licence, Record, SourceResult

BASE = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
LICENCE = Licence('Europe PMC terms of use (per-article licences vary)',
                  'https://europepmc.org/Copyright',
                  'Metadata reused with attribution; each record keeps its own licence where stated. '
                  'Abstracts are used for local processing only.')


def _page(http, query: str, cursor: str, size: int) -> dict:
    data = http.json(BASE, {'query': query, 'format': 'json', 'resultType': 'core',
                            'pageSize': size, 'cursorMark': cursor})
    # Europe PMC reports errors inside an HTTP 200 response: never read that as "no results".
    if 'errCode' in data or 'resultList' not in data:
        raise SourceError(f"Europe PMC error: {data.get('errMsg', 'response had no results list')}")
    return data


def search(names: list[str], http, max_per_category: int = 5000) -> SourceResult:
    res = SourceResult('europepmc', OK, licence=LICENCE)
    seen: dict[str, Record] = {}
    try:
        for cat, q in queries.europepmc(names).items():
            cursor, got, total = '*', 0, None
            while got < max_per_category:
                data = _page(http, q, cursor, min(1000, max_per_category - got))
                total = data.get('hitCount', 0) if total is None else total
                rows = data['resultList'].get('result', [])
                for r in rows:
                    key = f"{r.get('source')}:{r.get('id')}"
                    if key in seen:
                        seen[key].categories = sorted(set(seen[key].categories) | {cat})
                        continue
                    pts = (r.get('pubTypeList') or {}).get('pubType', [])
                    seen[key] = Record(
                        source='europepmc', source_id=key,
                        url=f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}",
                        kind='preprint' if r.get('source') == 'PPR' else 'publication',
                        title=r.get('title', ''), year=int(r['pubYear']) if str(r.get('pubYear', '')).isdigit() else None,
                        pmid=r.get('pmid', ''), pmcid=r.get('pmcid', ''), doi=(r.get('doi') or '').lower(),
                        publication_types=pts if isinstance(pts, list) else [pts],
                        categories=[cat], abstract=r.get('abstractText', ''),
                        licence=r.get('license', ''),
                        extra={'open_access': r.get('isOpenAccess') == 'Y',   # 'Y'/'N' strings
                               'full_text_in_epmc': r.get('inEPMC') == 'Y'})
                got += len(rows)
                nxt = data.get('nextCursorMark')
                if not rows or not nxt or nxt == cursor:
                    break
                cursor = nxt
            res.queries.append({'category': cat, 'query': q, 'total': total or 0, 'retrieved': got})
        res.records = list(seen.values())
    except SourceError as e:
        res.status, res.error = FAILED, str(e)
    return res
