# Unified Memory System

This document maps the canonical memory architecture and the compatibility
layers that feed it.

## Goal

All agents, tools, UI routes, and learning systems should be able to store and
retrieve memories through one canonical record shape while older stores keep
working during migration.

## Canonical Store

Canonical file:

```text
STATE_DIR/memory/unified_memory.json
```

Default `STATE_DIR` resolution is owned by `runtime/core/state_paths.py`.

Canonical modules:

- `runtime/memory/schema.py`
- `runtime/memory/unified_store.py`
- `runtime/memory/service.py`

Every canonical memory is a `MemoryRecord` with:

- identity: `id`, `schema_version`
- ownership: `tenant_id`, `user_id`
- placement: `memory_type`, `scope`, `project_id`, `session_id`, `task_id`
- source labels: `source`, `agent`, `topic`, `tags`
- trust/ranking: `confidence`, `importance`, `verified`, `feedback_score`
- privacy: `sensitive`, `visibility`
- usage: `created_at`, `updated_at`, `last_accessed`, `access_count`
- payload: `text`, `summary`, `metadata`

## Memory Types

Canonical schema accepts current runtime types and legacy manager types:

```text
semantic, episodic, procedural, outcome, preference, decision, failure,
research, money, forge, task, session, long_term, knowledge_graph, company,
skill, financial, tool_history, project, event_timeline, structured_db
```

Use:

- `semantic` for facts and durable knowledge.
- `episodic` for task runs and events.
- `procedural` for reusable steps and skills.
- `preference` for user/company preferences.
- `decision` for chosen plans and rationale.
- `failure` for failed attempts and avoid rules.
- `knowledge_graph` for imported knowledge-store entries.
- `long_term` for legacy `MemoryIndex` memories.

## Write Path

Primary write path:

```text
caller -> MemoryService.remember/store -> UnifiedMemoryStore.upsert
                                  -> ShortTermCache
                                  -> VectorStore when promotable
                                  -> StrategyStore for outcomes
                                  -> NativeGraphStore when available
```

Compatibility adapters now also write canonical records:

- `MemoryRouter`: routes legacy `store/retrieve/get/record_outcome` through `MemoryService`.
- `MemoryManager`: writes all 14 legacy manager memory types into canonical memory, while preserving old backends.
- `MemoryIndex`: writes `add_memory()` entries into canonical `long_term` memory.
- `KnowledgeStore`: writes topic/insight entries and embedded `entries[]` into canonical `knowledge_graph` memory.
- `NeuralMemoryManager`: writes neural `remember()` calls into canonical memory.

## Read Path

Primary read path:

```text
caller -> MemoryService.retrieve
       -> short-term cache keyword match
       -> unified canonical search
       -> vector search
       -> dedupe and score
```

Compatibility reads:

- `MemoryRouter.retrieve()` delegates to `MemoryService.retrieve()`.
- `MemoryManager.retrieve()` searches canonical memory and legacy stores, then prefers canonical duplicates.
- `MemoryIndex.get_relevant_memories()` merges canonical hits into ranked legacy results.
- `KnowledgeStore.search_knowledge()` and `get_relevant_context()` include canonical knowledge records.
- `NeuralMemoryManager.recall()` includes canonical hits as `source_store="unified"`.

## Labeling And Placement

Records are findable because every write should label:

- `tenant_id`: default tenant or active tenant.
- `memory_type`: what kind of memory it is.
- `scope`: inferred from project/session/agent/task labels when not explicit.
- `project_id`: project/workspace context.
- `session_id`: conversation/runtime session.
- `task_id`: task/run identifier.
- `agent`: producing agent or subsystem.
- `source`: module or integration that wrote the record.
- `topic` and `tags`: human/semantic lookup labels.

Retrieval filters can use tenant, type, scope, project, session, agent, and tags.

## Migration

Migration script:

```bash
python3 scripts/migrate_memory_to_unified.py
python3 scripts/migrate_memory_to_unified.py --apply
```

Dry-run is default. The script imports:

- `knowledge_store.json`
- `memory_index.json`
- `vector_store.json`
- `memory_preference.json`
- `memory_tool_history.json`
- `memory_project.json`

It uses stable IDs, skips records already in canonical memory, and writes only
with `--apply`.

## Merge Order

The PR stack should merge in this order:

1. Unified core schema/store/service.
2. MemoryManager adapter.
3. MemoryIndex adapter.
4. KnowledgeStore adapter.
5. NeuralMemoryManager adapter.
6. Legacy JSON migration script.
7. This documentation.

## Remaining Work

- Add API endpoints for canonical memory inspection and filtered search.
- Add dashboard panels backed by canonical memory stats and recent records.
- Add tenant-aware privacy controls before exposing shared/public memory.
- Add retention lifecycle support for `unified_memory.json`.
- Migrate any direct server-side vector writes to `MemoryService`.
