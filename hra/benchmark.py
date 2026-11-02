"""Scientific benchmark for the evidence engine.

    python -m hra.benchmark run                # live: needs internet and the ClinPGx download
    python -m hra.benchmark score WORKSHEET    # score a manually annotated worksheet

Reference standards (independent of the engine's own output)
-----------------------------------------------------------
A. Search completeness: the studies ClinPGx curators cite for a medicine are a human-curated
   set of relevant pharmacogenomic publications. Recall = share of them the literature search
   (PubMed + Europe PMC, without ClinPGx) retrieves. Missed studies are listed for review.
   The validation landmarks are also checked.
B. De-duplication: records that share a PMID are known duplicates. Their identifiers are then
   hidden and de-duplication re-run, to measure how well title matching alone recovers them
   (precision and recall). Studies merging two different PMIDs are listed for manual review.
C. Extraction against curation: ClinPGx curators record cohort sizes and biogeographical
   groups from the full text. Sample-size and population rules (which read the abstract only)
   are compared with them. This is an approximate reference: curators see more than the abstract.
D. Manual annotation: a blinded worksheet of sampled abstracts. A reviewer records what each
   abstract states; ``score`` computes precision, recall and F1 for every extraction field.
E. Runtime and cost per source. Phase 1 uses no paid services (cost £0).
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import geo
from .dedup import deduplicate
from .engine import search_medicine

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / 'verification' / 'benchmark'
MEDICINES = ['clopidogrel', 'warfarin', 'fluorouracil', 'tamoxifen', 'bisoprolol']
FIELDS = ['stated_sample_size', 'stated_population', 'stated_recruitment_country', 'stated_effect_estimate']

# Benchmark-only lookup used to compare free-text descriptors with ClinPGx groups.
# It is NEVER used by the product to assign ancestry; it only scores agreement.
DESCRIPTOR_GROUPS = {
    'European': ['european', 'caucasian', 'white', 'northern european', 'european american',
                 'ashkenazi', 'italian', 'spanish', 'dutch', 'german', 'french', 'british', 'swedish',
                 'danish', 'finnish', 'polish', 'greek', 'portuguese', 'norwegian', 'swiss', 'croatian',
                 'slovenian', 'serbian', 'czech', 'russian'],
    'East Asian': ['chinese', 'han chinese', 'japanese', 'korean', 'taiwanese', 'thai', 'vietnamese',
                   'malay', 'malaysian', 'filipino', 'indonesian', 'singaporean', 'east asian', 'asian'],
    'Central/South Asian': ['indian', 'pakistani', 'bangladeshi', 'sri lankan', 'nepali', 'nepalese',
                            'south asian', 'asian'],
    'Near Eastern': ['arab', 'egyptian', 'iranian', 'turkish', 'lebanese', 'saudi', 'emirati', 'jordanian',
                     'israeli', 'middle eastern', 'north african'],
    'Sub-Saharan African': ['nigerian', 'ghanaian', 'kenyan', 'ethiopian', 'ugandan', 'tanzanian',
                            'zimbabwean', 'south african', 'sub-saharan african', 'african', 'black'],
    'African American/Afro-Caribbean': ['african american', 'afro-caribbean', 'black'],
    'Latino': ['hispanic', 'latino', 'latina', 'latin american', 'mexican', 'brazilian', 'puerto rican',
               'colombian', 'peruvian', 'mixed ancestry'],
    'American': ['native american', 'american indian', 'alaska native', 'indigenous'],
    'Oceanian': ['aboriginal', 'torres strait islander', 'maori', 'pacific islander', 'polynesian'],
}


def descriptor_groups(text: str) -> set[str]:
    t = text.lower()
    return {g for g, words in DESCRIPTOR_GROUPS.items()
            if any(re.search(rf'\b{re.escape(w)}\b', t) for w in words)}


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else None
    rnd = lambda x: None if x is None else round(x, 3)  # noqa: E731
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': rnd(p), 'recall': rnd(r), 'f1': rnd(f)}


# ---- A. search completeness ------------------------------------------------
def completeness(gold_pmids: set[str], result) -> dict:
    lit = [r for r in result.records if r.source in ('pubmed', 'europepmc')]
    found_any = {r.pmid for r in lit if r.pmid}
    found_pgx = {r.pmid for r in lit if r.pmid and 'pgx' in r.categories}
    missed = sorted(gold_pmids - found_any, key=int)
    return {'reference_studies': len(gold_pmids),
            'recall_pgx_query': round(len(gold_pmids & found_pgx) / len(gold_pmids), 3) if gold_pmids else None,
            'recall_any_query': round(len(gold_pmids & found_any) / len(gold_pmids), 3) if gold_pmids else None,
            'missed_sample': missed[:25], 'missed_total': len(missed)}


# ---- B. de-duplication -----------------------------------------------------
def dedup_benchmark(records: list) -> dict:
    by_pmid: dict[str, list] = {}
    for r in records:
        if r.pmid and r.kind != 'trial':
            by_pmid.setdefault(r.pmid, []).append(r)
    pairs = {p: rs for p, rs in by_pmid.items() if len({x.source for x in rs}) > 1}
    # hide identifiers on the non-PubMed copies, then see if titles alone re-link them
    stripped = []
    truth = {}
    for r in records:
        if r.kind == 'trial':
            continue
        c = copy.deepcopy(r)
        if c.pmid in pairs and c.source != 'pubmed':
            truth[(c.source, c.source_id)] = c.pmid
            c.pmid = c.doi = c.pmcid = ''
            c.nct_ids, c.extra = [], {k: v for k, v in c.extra.items() if k != 'linked_pmids'}
        stripped.append(c)
    studies = deduplicate(stripped)
    tp = fp = fn = 0
    for s in studies:
        hidden = [truth[(x['source'], x['source_id'])] for x in s.sources if (x['source'], x['source_id']) in truth]
        pmids = set(s.identifiers['pmid'])
        for h in hidden:
            if h in pmids:
                tp += 1
            elif pmids:
                fp += 1          # merged into the wrong study
            else:
                fn += 1          # left on its own
    over = [s for s in deduplicate(list(records)) if len(s.identifiers['pmid']) > 1]
    return {'known_duplicate_pmids': len(pairs), 'title_matching_with_ids_hidden': prf(tp, fp, fn),
            'studies_merging_several_pmids': len(over),
            'several_pmid_sample_for_review': [{'key': s.key, 'pmids': s.identifiers['pmid'],
                                                'nct': s.identifiers['nct']} for s in over[:20]]}


# ---- C. extraction vs ClinPGx curation ----------------------------------------
def curated_reference(clinpgx_data, pmids: set[str]) -> dict[str, dict]:
    sp = clinpgx_data['study_populations']
    sp = sp[sp.pmid.isin(pmids)]
    ref = {}
    for pmid, g in sp.groupby('pmid'):
        import pandas as pd
        cases = pd.to_numeric(g.study_cases, errors='coerce')
        controls = pd.to_numeric(g.study_controls, errors='coerce')
        nums = {int(x) for x in pd.concat([cases, controls]).dropna() if x > 0}
        totals = cases.fillna(0) + controls.fillna(0)
        nums |= {int(x) for x in totals if x > 0}
        groups = set(g.population) - {'Unknown', 'Multiple groups', 'In vitro (no participants)'}
        ref[pmid] = {'numbers': nums, 'groups': groups}
    return ref


def extraction_vs_curation(result, ref: dict[str, dict]) -> dict:
    by_pmid = {}
    for e in result.extractions:
        for s in result.studies:
            if s.key == e.study_key:
                for p in s.identifiers['pmid']:
                    by_pmid.setdefault(p, []).append(e)
                break
    has_abs = {r.pmid for r in result.records if r.pmid and r.abstract}
    ss = {'tp': 0, 'fp': 0, 'fn': 0}
    pop = {'tp': 0, 'fp': 0, 'fn': 0}
    for pmid, cur in ref.items():
        if pmid not in has_abs:
            continue
        ex = by_pmid.get(pmid, [])
        sizes = {int(e.value) for e in ex if e.field == 'stated_sample_size' and e.value.isdigit()}
        if cur['numbers']:
            hit = {n for n in sizes if any(abs(n - c) <= 1 for c in cur['numbers'])}
            ss['tp'] += bool(hit)
            ss['fn'] += not hit
            ss['fp'] += len(sizes - hit)
        if cur['groups']:
            found = set()
            for e in ex:
                if e.field == 'stated_population':
                    gs = descriptor_groups(e.value)
                    if gs & cur['groups']:
                        found |= gs & cur['groups']
                    elif gs:
                        pop['fp'] += 1
            pop['tp'] += len(found)
            pop['fn'] += len(cur['groups'] - found)
    return {'reference': 'ClinPGx curated cohort sizes and biogeographical groups (from full text); '
                         'rules read abstracts only, so recall is a lower bound',
            'studies_compared': len([p for p in ref if p in has_abs]),
            'sample_size': {**prf(**ss), 'note': 'precision is a lower bound: abstracts state subgroup '
                                                 'numbers that curators do not record'},
            'population': prf(**pop)}


# ---- D. manual worksheet -----------------------------------------------------
def write_worksheet(results: list, n: int, out: Path, seed: int = 20261031, min_abstract: int = 200) -> Path:
    pool = [(res.report['medicine'], r) for res in results for r in res.records
            if r.source == 'pubmed' and len(r.abstract) > min_abstract]
    rnd = random.Random(seed)
    sample = rnd.sample(pool, min(n, len(pool)))
    out.mkdir(parents=True, exist_ok=True)
    ws, pred = out / 'annotation_worksheet.csv', out / 'predictions_hidden.csv'
    with open(ws, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['pmid', 'medicine', 'title', 'abstract', 'gold_sample_sizes', 'gold_populations',
                    'gold_recruitment_countries', 'gold_effect_estimates', 'reviewer', 'notes'])
        for m, r in sample:
            w.writerow([r.pmid, m, r.title, r.abstract, '', '', '', '', '', ''])
    from . import extract
    with open(pred, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['pmid', 'field', 'value', 'method'])
        for m, r in sample:
            for e in extract.from_abstract(f'pmid:{r.pmid}', r):
                w.writerow([r.pmid, e.field, e.value, e.method])
    return ws


def _norm_items(field: str, text: str) -> set[str]:
    parts = [p.strip() for p in re.split(r'[;\n]', text or '') if p.strip()]
    if field == 'stated_sample_size':
        return {p.replace(',', '') for p in parts}
    if field == 'stated_recruitment_country':
        return {geo.countries_in_text(p)[0] if geo.countries_in_text(p) else p.lower() for p in parts}
    if field == 'stated_effect_estimate':
        return {re.findall(r'\d+(?:\.\d+)?', p)[0] for p in parts if re.findall(r'\d+(?:\.\d+)?', p)}
    return {p.lower() for p in parts}


def score(worksheet: Path, predictions: Path | None = None) -> dict:
    predictions = predictions or worksheet.with_name('predictions_hidden.csv')
    gold_rows = [r for r in csv.DictReader(open(worksheet, encoding='utf-8')) if r.get('reviewer')]
    preds: dict[tuple, set] = {}
    for r in csv.DictReader(open(predictions, encoding='utf-8')):
        preds.setdefault((r['pmid'], r['field']), set()).add(r['value'])
    cols = {'stated_sample_size': 'gold_sample_sizes', 'stated_population': 'gold_populations',
            'stated_recruitment_country': 'gold_recruitment_countries',
            'stated_effect_estimate': 'gold_effect_estimates'}
    out = {}
    for field, col in cols.items():
        tp = fp = fn = 0
        for g in gold_rows:
            gold = _norm_items(field, g[col])
            got = _norm_items(field, ';'.join(preds.get((g['pmid'], field), set())))
            if field == 'stated_population':      # phrase overlap either way counts as a match
                matched = {x for x in got if any(x in y or y in x for y in gold)}
                tp += len(matched)
                fp += len(got - matched)
                fn += len({y for y in gold if not any(x in y or y in x for x in got)})
            else:
                tp += len(got & gold)
                fp += len(got - gold)
                fn += len(gold - got)
        out[field] = prf(tp, fp, fn)
    return {'annotated_abstracts': len(gold_rows), 'fields': out}


# ---- runner -------------------------------------------------------------------
def run(medicines=MEDICINES, worksheet_n: int = 40, out: Path = OUT, search=search_medicine,
        clinpgx_data=None) -> dict:
    import atlas
    data = clinpgx_data if clinpgx_data is not None else (
        atlas.load_live() if atlas.live_available() else None)
    if data is None:
        raise SystemExit('The benchmark needs the ClinPGx download: run python ingest.py first.')
    landmarks = [r for r in csv.DictReader(open(HERE / 'verification' / 'validation_v07.csv', encoding='utf-8'))
                 if r['check'] in ('landmark_pmid_found', 'landmark_trial_found')]
    report = {'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              'medicines': {}, 'cost_gbp': 0.0}
    results = []
    for m in medicines:
        print(f'Benchmarking {m} …', flush=True)
        res = search(m, sources=('chembl', 'pubmed', 'europepmc', 'clinicaltrials'),
                     max_per_category=9999, max_trials=5000)
        results.append(res)
        st = atlas.studies(data, m)
        gold = set(st.pmid)
        found_p = {p for s in res.studies for p in s.identifiers['pmid']}
        found_t = {n for s in res.studies for n in s.identifiers['nct']}
        lm = [{'id': r['expected'], 'found': r['expected'] in (found_p | found_t)}
              for r in landmarks if r['medicine'] == m]
        report['medicines'][m] = {
            'sources': [{k: s[k] for k in ('source', 'status', 'records_retrieved', 'total_hits_reported',
                                           'truncated', 'seconds', 'error')} for s in res.report['sources']],
            'records': res.report['totals']['records_retrieved'],
            'unique_studies': res.report['totals']['unique_studies'],
            'A_search_completeness': {**completeness(gold, res), 'landmarks': lm},
            'B_deduplication': dedup_benchmark(res.records),
            'C_extraction_vs_curation': extraction_vs_curation(res, curated_reference(data, gold)),
            'integrity': res.report['integrity'],
        }
    ws = write_worksheet(results, worksheet_n, out)
    report['D_manual_worksheet'] = str(ws)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'benchmark.json').write_text(json.dumps(report, indent=2), 'utf-8')
    (out / 'benchmark_report.md').write_text(to_markdown(report), 'utf-8')
    return report


def _pct(x):
    return '—' if x is None else f'{x:.0%}'


def to_markdown(rep: dict) -> str:
    L = ['# Human Response Atlas: scientific benchmark', '', f"Generated {rep['generated_at']}. "
         f"Cost of paid services: £{rep['cost_gbp']:.2f}.", '',
         '## A. Search completeness (reference: studies cited by ClinPGx curators)', '',
         '| Medicine | Reference studies | Recall: genetics query | Recall: any query | Landmarks found |',
         '|---|---|---|---|---|']
    for m, v in rep['medicines'].items():
        a = v['A_search_completeness']
        lm = ', '.join(f"{x['id']} {'✓' if x['found'] else '✗'}" for x in a['landmarks']) or '—'
        L.append(f"| {m} | {a['reference_studies']} | {_pct(a['recall_pgx_query'])} | {_pct(a['recall_any_query'])} | {lm} |")
    L += ['', '## B. De-duplication', '',
          '| Medicine | Known duplicate PMIDs | Title-only precision | Title-only recall | Studies merging several PMIDs |',
          '|---|---|---|---|---|']
    for m, v in rep['medicines'].items():
        b = v['B_deduplication']
        t = b['title_matching_with_ids_hidden']
        L.append(f"| {m} | {b['known_duplicate_pmids']} | {_pct(t['precision'])} | {_pct(t['recall'])} | "
                 f"{b['studies_merging_several_pmids']} |")
    L += ['', '## C. Extraction against ClinPGx curation (approximate; abstracts vs full text)', '',
          '| Medicine | Studies compared | Sample size P / R | Population P / R |', '|---|---|---|---|']
    for m, v in rep['medicines'].items():
        c = v['C_extraction_vs_curation']
        L.append(f"| {m} | {c['studies_compared']} | {_pct(c['sample_size']['precision'])} / "
                 f"{_pct(c['sample_size']['recall'])} | {_pct(c['population']['precision'])} / "
                 f"{_pct(c['population']['recall'])} |")
    L += ['', '## E. Runtime per source (seconds)', '', '| Medicine | ' + ' | '.join(
        s['source'] for s in next(iter(rep['medicines'].values()))['sources']) + ' |',
        '|---|' + '---|' * len(next(iter(rep['medicines'].values()))['sources'])]
    for m, v in rep['medicines'].items():
        L.append(f'| {m} | ' + ' | '.join(f"{s['seconds']:.0f}" for s in v['sources']) + ' |')
    L += ['', '## Evidence integrity', '']
    for m, v in rep['medicines'].items():
        i = v['integrity']
        L.append(f"- {m}: {'passed' if i['passed'] else 'FAILED'} ({i['checked_claims']:,} claims checked)")
    L += ['', '## D. Manual annotation', '',
          f"A blinded worksheet of sampled abstracts is at `{rep.get('D_manual_worksheet', '')}`. A reviewer fills in "
          'the gold columns (separate several values with semicolons) and their name, then runs '
          '`python -m hra.benchmark score <worksheet>`.']
    if rep.get('D_scores'):
        L += ['', f"{rep['D_scores']['annotated_abstracts']} abstracts annotated.", '',
              '| Field | Precision | Recall | F1 |', '|---|---|---|---|']
        for f, s in rep['D_scores']['fields'].items():
            L.append(f"| {f} | {_pct(s['precision'])} | {_pct(s['recall'])} | {_pct(s['f1'])} |")
    return '\n'.join(L) + '\n'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python -m hra.benchmark')
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--medicines', default=','.join(MEDICINES))
    r.add_argument('--worksheet-size', type=int, default=40)
    s = sub.add_parser('score')
    s.add_argument('worksheet')
    a = ap.parse_args(argv)
    if a.cmd == 'run':
        rep = run(a.medicines.split(','), a.worksheet_size)
        print(f"\nReport: {OUT / 'benchmark_report.md'}\nWorksheet: {rep['D_manual_worksheet']}")
        return 0
    ws = Path(a.worksheet)
    scores = score(ws)
    rep_file = ws.with_name('benchmark.json')
    rep = json.loads(rep_file.read_text('utf-8')) if rep_file.exists() else {
        'generated_at': '', 'medicines': {}, 'cost_gbp': 0.0}
    rep['D_scores'] = scores
    rep_file.write_text(json.dumps(rep, indent=2), 'utf-8')
    if rep['medicines']:
        ws.with_name('benchmark_report.md').write_text(to_markdown(rep), 'utf-8')
    print(json.dumps(scores, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
