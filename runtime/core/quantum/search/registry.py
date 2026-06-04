from __future__ import annotations
import importlib
import logging

log = logging.getLogger(__name__)

ENGINE_CONFIG: dict[str, dict] = {
    'searxng':      {'module': '.engines.searxng',       'class': 'SearxngEngine',       'bangs': ['web', 'news'],   'enabled': True},
    'local_memory': {'module': '.engines.local_memory',  'class': 'LocalMemoryEngine',   'bangs': ['memory', 'rag'], 'enabled': True},
    'mem0':         {'module': '.engines.mem0_memory',   'class': 'Mem0MemoryEngine',    'bangs': ['memory'],        'enabled': True},
    'neo4j':        {'module': '.engines.neo4j_graph',   'class': 'Neo4jGraphEngine',    'bangs': ['graph'],         'enabled': True},
    'codebase':     {'module': '.engines.codebase',      'class': 'CodebaseSearchEngine','bangs': ['code'],          'enabled': True},
    'docs':         {'module': '.engines.docs',          'class': 'DocsSearchEngine',    'bangs': ['doc'],           'enabled': True},
    'tasks':        {'module': '.engines.tasks',         'class': 'TaskHistoryEngine',   'bangs': ['task'],          'enabled': True},
    'agents':       {'module': '.engines.agents',        'class': 'AgentRegistryEngine', 'bangs': ['agent'],         'enabled': True},
    'tools':        {'module': '.engines.tools',         'class': 'ToolRegistryEngine',  'bangs': ['tool'],          'enabled': True},
    'logs':         {'module': '.engines.logs',          'class': 'ExecutionLogEngine',  'bangs': ['log'],           'enabled': True},
    'tests':        {'module': '.engines.tests',         'class': 'TestLogEngine',       'bangs': ['test'],          'enabled': True},
    'artifacts':    {'module': '.engines.artifacts',     'class': 'ArtifactEngine',      'bangs': ['artifact'],      'enabled': True},
}

# Root package name for relative imports
_PACKAGE = 'core.quantum.search'


class EngineRegistry:
    """Lazy-loads engine instances on first get_engines() call."""

    def __init__(self) -> None:
        self._instances: dict[str, object] | None = None

    def _load(self) -> dict[str, object]:
        instances: dict[str, object] = {}
        for name, cfg in ENGINE_CONFIG.items():
            if not cfg['enabled']:
                continue
            try:
                mod = importlib.import_module(cfg['module'], package=_PACKAGE)
                cls = getattr(mod, cfg['class'])
                instances[name] = cls()
            except Exception as exc:
                log.debug('Engine %s skipped: %s', name, exc)
        return instances

    def get_engines(self, bangs: list[str] | None = None) -> dict[str, object]:
        """Return engine instances. If bangs is non-empty, filter to matching engines.

        `bangs` may contain either engine names (e.g. 'agents') or bang tokens
        (e.g. 'agent') — both forms are supported.
        """
        if self._instances is None:
            self._instances = self._load()

        if not bangs:
            return dict(self._instances)

        bang_set = set(bangs)
        return {
            name: inst
            for name, inst in self._instances.items()
            # Match by engine name OR by bang token
            if name in bang_set or bang_set.intersection(ENGINE_CONFIG[name]['bangs'])
        }
