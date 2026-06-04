from __future__ import annotations
from ..schema import NormalizedSearchResult, SearchRequest
from ..bang import BangParser


class BangParserPlugin:
    """Parse !bang tokens from query, set request.bangs, remove bangs from query string."""

    def __init__(self) -> None:
        self._parser = BangParser()

    async def process(
        self,
        pool: list[NormalizedSearchResult],
        request: SearchRequest,
    ) -> tuple[list[NormalizedSearchResult], SearchRequest]:
        cleaned_query, engines = self._parser.parse(request.query)
        request.query = cleaned_query
        if engines:
            request.bangs = engines
        return pool, request
