"""Run the manually reviewed validation set (verification/validation_v07.csv).

    python -m hra.validate            # full live check (needs internet)
    python -m hra.validate --offline  # only checks that need no internet (local ClinPGx/CPIC)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .classify import ESTABLISHED, LIMITED
from .engine import search_medicine

HERE = Path(__file__).resolve().parents[1]
CASES = HERE / 'verification' / 'validation_v07.csv'


def check(row: dict, res) -> tuple[bool, str]:
    rep, kind, exp = res.report, row['check'], row['expected']
    established = {g['gene'] for g in rep['genes'] if g['category'] == ESTABLISHED}
    if kind == 'gene_established':
        want = set(exp.split(';'))
        return want <= established, f'established: {", ".join(sorted(established)) or "none"}'
    if kind == 'no_gene_established':
        return not established, f'established: {", ".join(sorted(established)) or "none"}'
    if kind == 'trade_name_resolves':
        tn = (rep['identity'] or {}).get('trade_names', [])
        return exp.lower() in {t.lower() for t in tn}, f'trade names: {", ".join(tn[:8]) or "none"}'
    if kind == 'landmark_pmid_found':
        found = {p for s in res.studies for p in s.identifiers['pmid']}
        note = '; '.join(f"{s['source']} {s['records_retrieved']:,}/{s['total_hits_reported']:,}"
                         + (' TRUNCATED' if s['truncated'] else '')
                         for s in rep['sources'] if s['source'] in ('pubmed', 'europepmc'))
        return exp in found, f'{len(found):,} PMIDs retrieved ({note})'
    if kind == 'landmark_trial_found':
        found = {n for s in res.studies for n in s.identifiers['nct']}
        return exp in found, f'{len(found):,} trial IDs retrieved'
    if kind == 'curated_ancestry_includes':
        groups = rep['population']['curated_ancestry_groups (ClinPGx, curator-reviewed)']
        return groups.get(exp, 0) > 0, f'{exp}: {groups.get(exp, 0)} studies'
    if kind == 'efficacy_trials_and_reviews_found':
        e = rep['evidence_categories']['efficacy']
        ok = e['randomised_trials'] >= 1 and e['reviews_or_meta_analyses'] >= 1 and e['category'] != LIMITED
        return ok, (f"{e['randomised_trials']} RCTs, {e['reviews_or_meta_analyses']} reviews; "
                    f"classified {e['category']} ({e['method']})")
    return False, f'unknown check {kind}'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python -m hra.validate')
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--out', default=str(HERE / 'verification' / 'validation_report.md'))
    a = ap.parse_args(argv)
    rows = list(csv.DictReader(open(CASES, encoding='utf-8')))
    if a.offline:
        rows = [r for r in rows if r['needs_live_search'] == 'no']
    sources = ('clinpgx',) if a.offline else ('chembl', 'clinpgx', 'pubmed', 'europepmc', 'clinicaltrials')
    cache, lines, failed = {}, [], 0
    for r in rows:
        m = r['medicine']
        if m not in cache:
            print(f'Searching {m} …', flush=True)
            cache[m] = search_medicine(m, sources=sources, max_per_category=9999, max_trials=5000)
        ok, detail = check(r, cache[m])
        failed += not ok
        lines.append(f"| {m} | {r['check']} | {r['expected']} | {'PASS' if ok else 'FAIL'} | {detail} | {r['source_of_truth']} |")
        print(f"[{'PASS' if ok else 'FAIL'}] {m}: {r['check']} {r['expected']} — {detail}")
    status = []
    for m, res in cache.items():
        for s in res.report['sources']:
            status.append(f"| {m} | {s['source']} | {s['status']} | {s['records_retrieved']} | {s['error']} |")
    Path(a.out).write_text('\n'.join([
        '# Validation report (v0.7)', '',
        f'{len(rows) - failed} of {len(rows)} checks passed ({"offline" if a.offline else "live"} run).', '',
        '| Medicine | Check | Expected | Result | Detail | Source of truth |', '|---|---|---|---|---|---|',
        *lines, '', '## Source status', '', '| Medicine | Source | Status | Records | Error |',
        '|---|---|---|---|---|', *status, '']), 'utf-8')
    print(f'\n{len(rows) - failed} of {len(rows)} passed. Report: {a.out}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
