"""Verb: web-search — placeholder.

Pure-Python web search needs an API key (Google Custom Search, Bing, Brave,
Tavily, etc.) or a fragile HTML scraper. We have neither configured.

Until a search backend is wired, this verb returns a clear error pointing
the caller at their own search tool. The proof-explorer agent has the
WebSearch tool natively; it can call that directly and pass results to
other verbs (e.g., index-source) if it needs the audit trail.

To enable: pick a backend (e.g., Tavily — set TAVILY_API_KEY), implement
the call here, and update the README.
"""

from __future__ import annotations


def run(args: dict, request_id: str) -> dict:
    """args: {"query": str, "k": int, "recency_days": int?}"""
    query = args.get("query")
    if not query:
        raise ValueError("missing required field: query")
    raise NotImplementedError(
        "web-search has no backend configured. "
        "Use the caller's WebSearch tool directly, or wire a backend "
        "(Tavily / Brave / Google CSE) into engineers/lib/verbs/web_search.py."
    )
