"""Plain data structures shared by every part of the engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

OK, FAILED, NOT_SEARCHED, UNAVAILABLE = 'searched', 'failed', 'not searched', 'unavailable'

UNVERIFIED = 'unverified'          # extracted automatically, not yet checked by a person
SOURCE_STRUCTURED = 'source-structured'   # a field the database itself provides


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Licence:
    name: str
    url: str
    notes: str = ''


@dataclass
class Record:
    """One item returned by one source (an article, a trial, an annotation)."""
    source: str                    # e.g. 'pubmed', 'europepmc', 'clinicaltrials', 'clinpgx'
    source_id: str                 # identifier in that source
    url: str
    kind: str                      # 'publication' | 'trial' | 'annotation'
    title: str = ''
    year: int | None = None
    pmid: str = ''
    pmcid: str = ''
    doi: str = ''
    nct_ids: list[str] = field(default_factory=list)
    publication_types: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)   # pgx / efficacy / safety (query matched)
    abstract: str = ''             # kept for local extraction; never exported in full
    licence: str = ''              # per-record licence where the source states one
    countries: list[str] = field(default_factory=list)     # trial site countries (registry)
    enrollment: int | None = None
    registry_race_ethnicity: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    retrieved_at: str = field(default_factory=now_utc)


@dataclass
class SourceResult:
    source: str
    status: str                    # OK / FAILED / NOT_SEARCHED / UNAVAILABLE
    queries: list[dict] = field(default_factory=list)   # [{'category', 'query', 'total', 'retrieved'}]
    records: list[Record] = field(default_factory=list)
    error: str = ''
    licence: Licence | None = None
    retrieved_at: str = field(default_factory=now_utc)
    seconds: float = 0.0

    @property
    def total_hits(self) -> int:
        return sum(q.get('total', 0) or 0 for q in self.queries)


@dataclass
class Extraction:
    """One extracted fact with everything needed to check it by hand."""
    study_key: str
    field: str                     # 'sample_size' | 'population_description' | ...
    value: str
    source: str
    source_id: str
    quote: str                     # the exact text the value came from
    location: str                  # where in the document: 'abstract[120:164]', 'registry baseline'
    method: str                    # 'rule:sample_size_v1', 'registry-structured', ...
    status: str = UNVERIFIED


@dataclass
class Study:
    """A unique study after de-duplication, with every source that reported it."""
    key: str
    title: str
    year: int | None
    kind: str
    identifiers: dict              # {'pmid': [...], 'doi': [...], 'pmcid': [...], 'nct': [...]}
    sources: list[dict]            # [{'source', 'source_id', 'url'}]
    categories: list[str]
    publication_types: list[str]
    countries: list[str]           # registered trial-site countries only
    enrollment: int | None
    registry_race_ethnicity: list[dict]
    licence_notes: list[str]
    trial_has_results: bool = False
    extractions: list[Extraction] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d
