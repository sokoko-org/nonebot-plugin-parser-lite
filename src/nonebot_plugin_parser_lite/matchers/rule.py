"""Text matching types retained at the original module path."""

from ..pipeline import MatchResult, match

SearchResult = MatchResult
UrlSearchResult = MatchResult

__all__ = ["MatchResult", "SearchResult", "UrlSearchResult", "match"]
