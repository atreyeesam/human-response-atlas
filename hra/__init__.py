"""Human Response Atlas evidence-discovery engine.

Usable without the Streamlit app:

    from hra import search_medicine
    result = search_medicine("clopidogrel")
    result.write_report("reports/")

or from the command line: ``python -m hra search clopidogrel --out reports``.
"""
__version__ = "0.10.0"



def search_medicine(*args, **kwargs):
    """Search every connected source for one medicine. See hra.engine.search_medicine."""
    from .engine import search_medicine as _search
    return _search(*args, **kwargs)
