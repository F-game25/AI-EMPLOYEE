from __future__ import annotations
import re
from ..schema import NormalizedSearchResult, SearchRequest


class QueryCleanerPlugin:
    """Normalize query whitespace and strip leading/trailing punctuation.
    Does NOT remove stopwords — they matter for code/agent searches.
    """

    _LEADING_TRAIL_PUNCT = re.compile(r'^[\W_]+|[\W_]+$')

    async def process(
        self,
        pool: list[NormalizedSearchResult],
        request: SearchRequest,
    ) -> tuple[list[NormalizedSearchResult], SearchRequest]:
        query = request.query
        # Normalize whitespace
        query = re.sub(r'\s+', ' ', query).strip()
        # Strip leading/trailing punctuation (but keep internal)
        query = self._LEADING_TRAIL_PUNCT.sub('', query).strip()
        request.query = query
        return pool, request
