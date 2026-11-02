"""Evidence-gap report: report.json, studies.csv, extractions.csv, sources.csv, report.html."""
from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from .engine import studies_rows, write_csv

E = html.escape
INCLUSION = [
    'Publications whose title or abstract names the medicine (generic name, recognised synonyms or '
    'trade names), retrieved from PubMed and Europe PMC with the category filters shown.',
    'Registered studies on ClinicalTrials.gov listing the medicine as an intervention.',
    'Studies cited as evidence by ClinPGx annotations for the medicine (local ClinPGx download).',
    'No language, date or design restrictions beyond those in the queries.',
]


def _table(rows: list[dict], cols: list[tuple[str, str]], link: str | None = None) -> str:
    head = ''.join(f'<th>{E(t)}</th>' for _, t in cols)
    body = ''
    for r in rows:
        cells = ''
        for k, _ in cols:
            v = r.get(k, '')
            v = '' if v is None else v
            if k == link and r.get('_url'):
                cells += f'<td><a href="{E(r["_url"])}">{E(str(v))}</a></td>'
            else:
                cells += f'<td>{E(str(v))}</td>'
        body += f'<tr>{cells}</tr>'
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _evidence_links(keys: list[str], limit: int = 12) -> str:
    out = []
    for k in keys[:limit]:
        kind, _, ident = k.partition(':')
        url = {'pmid': f'https://pubmed.ncbi.nlm.nih.gov/{ident}/',
               'nct': f'https://clinicaltrials.gov/study/{ident}',
               'doi': f'https://doi.org/{ident}'}.get(kind)
        out.append(f'<a href="{E(url)}">{E(k)}</a>' if url else E(k))
    more = f' and {len(keys) - limit} more (see report.json)' if len(keys) > limit else ''
    return ', '.join(out) + more


def _dict_list(d) -> str:
    if not d:
        return '<p class="muted">None recorded in the searched sources.</p>'
    if isinstance(d, (int, float)):
        return f'<p>{d:,}</p>'
    items = []
    for k, v in list(d.items())[:25]:
        if isinstance(v, dict):
            items.append(f'<li>{E(str(k))}: <b>{v["count"]:,} {E(v["unit"])}</b>'
                         f'<br><span class="muted">Evidence: {_evidence_links(v["evidence"])}</span></li>')
        else:
            items.append(f'<li>{E(str(k))}: <b>{E(str(v))}</b></li>')
    return '<ul>' + ''.join(items) + '</ul>'


def to_html(result) -> str:
    r = result.report
    srcs = _table([{**s, 'queries_n': len(s['queries'])} for s in r['sources']],
                  [('source', 'Source'), ('status', 'Status'), ('records_retrieved', 'Records retrieved'),
                   ('total_hits_reported', 'Hits reported'), ('truncated', 'Truncated'),
                   ('error', 'Error'), ('retrieved_at', 'Searched at')])
    qs = ''.join(f'<li><b>{E(s["source"])} · {E(q.get("category", ""))}</b> '
                 f'({q.get("total", 0):,} hits, {q.get("retrieved", 0):,} retrieved)'
                 f'<pre>{E(q.get("query", ""))}</pre></li>'
                 for s in r['sources'] for q in s['queries'])
    cats = _table([{'category_name': k, **v} for k, v in r['evidence_categories'].items()],
                  [('category_name', 'Evidence type'), ('category', 'Classification'), ('method', 'Method'),
                   ('unique_studies', 'Relevant unique studies'), ('reason', 'Why'),
                   ('partial_search', 'Partial search')])
    cats += ''.join(f'<p class="muted"><b>{E(k)}</b> evidence: '
                    f'{_evidence_links(v["supporting"].get("reviewed_pmids") and ["pmid:" + p for p in v["supporting"]["reviewed_pmids"]] or v["supporting"]["studies"])}</p>'
                    for k, v in r['evidence_categories'].items() if v['supporting']['studies'] or v['supporting'].get('reviewed_pmids'))
    gene_rows = [{**g, 'evidence': '; '.join(f"{c['type']} {c['id']}" for c in g.get('supporting', [])[:4])}
                 for g in r['genes']]
    genes = _table(gene_rows, [('gene', 'Gene'), ('category', 'Classification'), ('reason', 'Why'),
                               ('evidence', 'Supporting evidence'), ('cpic_level', 'CPIC level'),
                               ('clinpgx_best_level', 'ClinPGx best level')]) if r['genes'] else \
        '<p class="muted">No ClinPGx gene annotations (or ClinPGx not searched).</p>'
    pop = ''.join(f'<h3>{E(k)}</h3>{_dict_list(v)}' for k, v in r['population'].items())
    geo = ''.join(f'<h3>{E(k)}</h3>{_dict_list(v)}' for k, v in r['geography'].items())
    rows = []
    for s in studies_rows(result.studies)[:300]:
        rows.append({**s, '_url': s['source_links'].split(' ')[0]})
    studies = _table(rows, [('title', 'Study'), ('year', 'Year'), ('found_in', 'Found in'),
                            ('categories', 'Evidence type'), ('pmids', 'PMID'), ('nct_ids', 'Trial ID')],
                     link='title')
    rules = ''.join(f'<h3>{E(k)}</h3><ul>' + ''.join(f'<li>{E(x)}</li>' for x in v) + '</ul>'
                    for k, v in r['classification_rules'].items())
    lic = ''.join(f'<li><b>{E(s["source"])}</b>: {E(s["licence"]["name"])} — '
                  f'<a href="{E(s["licence"]["url"])}">{E(s["licence"]["url"])}</a>. {E(s["licence"]["notes"])}</li>'
                  for s in r['sources'] if s.get('licence'))
    ident = r['identity'] or {}
    return f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence-gap report: {E(r['medicine'])}</title>
<style>
body{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#1f2a37;background:#fff;
max-width:980px;margin:0 auto;padding:24px 16px;line-height:1.55}}
h1{{font-size:1.8rem;margin:.2rem 0}} h2{{margin-top:2rem;border-top:1px solid #d3dad8;padding-top:1rem}}
h3{{font-size:1rem;margin:1rem 0 .3rem}} .muted{{color:#5b6775}} pre{{white-space:pre-wrap;background:#f2f5f4;
padding:.5rem;border-radius:4px;font-size:.8rem}} .tw{{overflow-x:auto}} table{{border-collapse:collapse;
width:100%;font-size:.88rem}} th,td{{border-bottom:1px solid #e1e5e4;padding:.35rem .5rem;text-align:left;
vertical-align:top}} th{{background:#f2f5f4}} .box{{border-left:3px solid #c98f12;padding:.4rem 1rem;
background:#fbf7ee}} a{{color:#0e6e6b}}
</style></head><body>
<p class="muted">Human Response Atlas · evidence-gap report · engine v{E(r['engine_version'])}</p>
<h1>{E(r['medicine'].capitalize())}</h1>
<p><b>Research question.</b> {E(r['question'])}</p>
<p class="muted">Searched {E(r['started_at'])} to {E(r['finished_at'])}. Fingerprint {E(r['fingerprint'])}.
Standardised identity: {E(ident.get('chembl_id', 'not resolved'))}{(' · trade names: ' + E(', '.join(ident.get('trade_names', [])[:8]))) if ident.get('trade_names') else ''}.
Searched under: {E(', '.join(r['search_names']))}.</p>
<div class="box"><p><b>Read this first.</b> This report describes what was found in the sources listed, on the
date shown. It is not a judgement on whether the medicine works for any person, and a missing record is not
proof that research does not exist. Not for clinical use.</p></div>
<h2>Evidence check</h2><p>{'Passed: all ' + format(r['integrity']['checked_claims'], ',') + ' claims trace to identifiable studies, annotations or guidelines.' if r.get('integrity', {}).get('passed') else 'FAILED: ' + E('; '.join(r.get('integrity', {}).get('problems', [])[:10]))}</p>
<h2>Databases searched</h2>{srcs}
<h2>Exact search terms</h2><ul>{qs}</ul>
<h3>Inclusion criteria</h3><ul>{''.join(f'<li>{E(x)}</li>' for x in INCLUSION)}</ul>
<h2>Records and unique studies</h2>
<p>{r['totals']['records_retrieved']:,} records retrieved; <b>{r['totals']['unique_studies']:,} unique studies</b>
after de-duplication by PMID, DOI, PMCID, trial registration number and title.</p>
<h2>Evidence classification</h2>{cats}
<h2>Pharmacogenomic associations</h2>{genes}
<h2>Population representation</h2>{pop}
<h2>Geography</h2><p class="muted">Four layers, never merged: registered trial sites, author locations,
populations described, and places indexed by PubMed (not proof of recruitment).</p>{geo}
<h2>Unresolved questions</h2><ul>{''.join(f'<li>{E(x)}</li>' for x in r['unresolved_questions']) or '<li>None identified by the current rules.</li>'}</ul>
<h2>Strengths and limitations</h2><ul>{''.join(f'<li>{E(x)}</li>' for x in r['limitations'])}</ul>
<h2>Studies</h2><p class="muted">Up to 300 shown; the full list is in studies.csv.</p>{studies}
<h2>Method: classification rules</h2>{rules}
<h2>Reproduce</h2><pre>{E(r['reproduce'])}</pre>
<h2>Sources and licences</h2><ul>{lic}</ul>
<p class="muted">Data from ClinPGx (PharmGKB® and CPIC®) are CC BY-NC-SA 4.0, non-commercial use only; anyone
receiving derived data must first agree to that licence. ChEMBL data are CC BY-SA 3.0. Bibliographic data
courtesy of the U.S. National Library of Medicine. ClinicalTrials.gov records are provided by sponsors and are
not verified by NLM. No source endorses this report.</p>
</body></html>"""


def write_all(result, out: Path) -> Path:
    slug = ''.join(c if c.isalnum() else '-' for c in result.report['medicine']).strip('-')
    d = out / f"{slug}_{result.report['started_at'][:10]}"
    d.mkdir(parents=True, exist_ok=True)
    (d / 'report.json').write_text(json.dumps({
        **result.report, 'studies': [s.to_dict() for s in result.studies]}, indent=2, default=str), 'utf-8')
    write_csv(d / 'studies.csv', studies_rows(result.studies))
    write_csv(d / 'extractions.csv', [asdict(e) for e in result.extractions])
    write_csv(d / 'sources.csv', [{k: v for k, v in s.items() if k not in ('queries', 'licence')} |
                                  {'licence': (s.get('licence') or {}).get('name', '')}
                                  for s in result.report['sources']])
    (d / 'report.html').write_text(to_html(result), 'utf-8')
    return d
