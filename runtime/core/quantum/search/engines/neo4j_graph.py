from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
_BRAIN_GRAPH_PATH = os.path.join(_REPO_ROOT, 'state', 'brain_graph.json')


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


class Neo4jGraphEngine:
    name = 'neo4j'
    source_type = 'graph_memory'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('Neo4jGraphEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        # Try live Neo4j first
        try:
            return self._neo4j_search(request)
        except Exception as exc:
            log.debug('Neo4j live query failed (%s), falling back to brain_graph.json', exc)

        # Fallback: brain_graph.json
        return self._file_fallback(request)

    def _neo4j_search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        import neo4j as _neo4j  # noqa: F401 — raises ImportError if not installed
        from neo4j import GraphDatabase

        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        user = os.environ.get('NEO4J_USER', 'neo4j')
        password = os.environ.get('NEO4J_PASSWORD', 'neo4j')

        driver = GraphDatabase.driver(uri, auth=(user, password))
        tokens = request.query.lower().split()
        results = []

        with driver.session() as session:
            cypher = (
                'MATCH (n) WHERE toLower(n.name) CONTAINS $term OR toLower(coalesce(n.description,"")) CONTAINS $term '
                'RETURN n LIMIT $limit'
            )
            for token in tokens[:3]:  # Use first 3 tokens to avoid too-broad queries
                records = session.run(cypher, term=token, limit=request.max_results_per_engine)
                for rec in records:
                    node = rec['n']
                    props = dict(node)
                    label = list(node.labels)[0] if node.labels else 'node'
                    title = props.get('name', props.get('id', label))
                    content = str(props.get('description', props.get('content', str(props))))[:500]
                    neighbors = []
                    uid = hashlib.md5(f"neo4j:{node.id}".encode()).hexdigest()[:12]
                    results.append(NormalizedSearchResult(
                        id=uid, title=str(title), content=content,
                        url=f'neo4j://node/{node.id}',
                        source_type='graph_memory', engine=self.name,
                        score=0.6, graph_neighbors=neighbors,
                        metadata={'label': label, 'node_id': node.id},
                    ))

        driver.close()
        # Deduplicate by id
        seen: set[str] = set()
        unique = []
        for r in results:
            if r.id not in seen:
                seen.add(r.id)
                unique.append(r)
        return unique[:request.max_results_per_engine]

    def _file_fallback(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        if not os.path.exists(_BRAIN_GRAPH_PATH):
            return []
        try:
            with open(_BRAIN_GRAPH_PATH) as f:
                data = json.load(f)
        except Exception as exc:
            log.debug('brain_graph.json read error: %s', exc)
            return []

        tokens = request.query.lower().split()
        nodes = data.get('nodes', data if isinstance(data, list) else [])
        edges = data.get('edges', data.get('relationships', []))

        # Build adjacency for graph_neighbors
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            src = str(edge.get('from', edge.get('source', '')))
            tgt = str(edge.get('to', edge.get('target', '')))
            adjacency.setdefault(src, []).append(tgt)
            adjacency.setdefault(tgt, []).append(src)

        results = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            label = node.get('label', node.get('type', 'node'))
            title = node.get('name', node.get('id', str(label)))
            description = node.get('description', node.get('content', ''))
            combined = f"{label} {title} {description}"
            score = _keyword_score(tokens, combined)
            if score == 0.0:
                continue
            node_id = str(node.get('id', title))
            uid = hashlib.md5(f"graph:{node_id}".encode()).hexdigest()[:12]
            neighbors = adjacency.get(node_id, [])[:5]
            results.append(NormalizedSearchResult(
                id=uid, title=str(title), content=str(description)[:500],
                url=_BRAIN_GRAPH_PATH,
                source_type='graph_memory', engine=self.name,
                score=score, graph_neighbors=neighbors,
                metadata={'label': label, 'node_id': node_id},
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]
