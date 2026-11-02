"""Command line: python -m hra search <medicine> [--out reports] [--max 200] [--max-trials 300]"""
import argparse
import sys

from .engine import search_medicine


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python -m hra', description='Human Response Atlas evidence search')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('search', help='search every connected source for one medicine')
    s.add_argument('medicine')
    s.add_argument('--out', default='reports')
    s.add_argument('--max', type=int, default=5000, help='records per query and category (PubMed allows up to 9,999)')
    s.add_argument('--max-trials', type=int, default=2000)
    s.add_argument('--sources', default='chembl,clinpgx,pubmed,europepmc,clinicaltrials')
    a = ap.parse_args(argv)
    res = search_medicine(a.medicine, sources=tuple(a.sources.split(',')),
                          max_per_category=a.max, max_trials=a.max_trials, log=print)
    for s_ in res.report['sources']:
        print(f"{s_['source']:<15} {s_['status']:<13} {s_['records_retrieved']:>6} records"
              + (f"  ({s_['error']})" if s_['error'] else '') + ('  [truncated]' if s_['truncated'] else ''))
    t = res.report['totals']
    print(f"\n{t['records_retrieved']:,} records -> {t['unique_studies']:,} unique studies")
    for k, v in res.report['evidence_categories'].items():
        print(f"  {k:<9} {v['category']} ({v['reason']})")
    print(f'\nReport written to {res.write_report(a.out)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
