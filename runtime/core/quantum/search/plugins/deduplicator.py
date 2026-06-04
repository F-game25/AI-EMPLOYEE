from __future__ import annotations
from ..schema import NormalizedSearchResult, SearchRequest


class DeduplicatorPlugin:
    """Dedup results by exact id, then by url (keep highest score)."""

    async def process(
        self,
        pool: list[NormalizedSearchResult],
        request: SearchRequest,
    ) -> tuple[list[NormalizedSearchResult], SearchRequest]:
        # Step 1: exact id dedup — keep first occurrence (results already sorted by score desc)
        seen_ids: set[str] = set()
        id_deduped: list[NormalizedSearchResult] = []
        for r in pool:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                id_deduped.append(r)

        # Step 2: url dedup — keep the one with higher score
        url_best: dict[str, NormalizedSearchResult] = {}
        no_url: list[NormalizedSearchResult] = []
        for r in id_deduped:
            if not r.url:
                no_url.append(r)
            elif r.url not in url_best or r.score > url_best[r.url].score:
                url_best[r.url] = r

        deduped = list(url_best.values()) + no_url
        deduped.sort(key=lambda r: r.score, reverse=True)
        return deduped, request
