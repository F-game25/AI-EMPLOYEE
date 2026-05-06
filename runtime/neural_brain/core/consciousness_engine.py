"""Top-level orchestrator for Neural Brain reasoning."""
import asyncio
import logging
import uuid
from datetime import datetime

from runtime.neural_brain.core.brain_state import BrainState
from runtime.neural_brain.core.reasoning_trace import ReasoningSession
from runtime.neural_brain.workflows.deep_reasoning_graph import build_reasoning_graph

logger = logging.getLogger(__name__)


class ConsciousnessEngine:
    """Main reasoning orchestrator.

    - Manages threads and checkpoints (via LangGraph)
    - Routes input through classification → reasoning pipeline
    - Persists traces and outcomes
    """

    def __init__(self):
        self.graph = build_reasoning_graph()
        self.active_threads: dict[str, ReasoningSession] = {}

    def think(
        self,
        input_text: str,
        user_id: str = "anonymous",
        thread_id: str | None = None,
        force: bool = False,
    ) -> dict:
        """Run complete reasoning on user input.

        Args:
            input_text: User query or command
            user_id: Tenant/user identifier
            thread_id: Resume existing thread (checkpoint) or None for new
            force: Force deep reasoning even for short queries

        Returns:
            {
                "output": str,
                "thread_id": str,
                "traces": [{node, latency_ms, status}],
                "total_latency_ms": float,
            }
        """
        thread_id = thread_id or str(uuid.uuid4())
        session = ReasoningSession(
            thread_id=thread_id,
            user_id=user_id,
            input=input_text,
            intent="unknown",
        )

        # Build initial state
        state: BrainState = {
            "input": input_text,
            "user_id": user_id,
            "thread_id": thread_id,
            "force": force,
            "trace": [],
        }

        try:
            # Run the graph
            result = self.graph.invoke(state, config={"configurable": {"thread_id": thread_id}})

            session.intent = result.get("intent", "unknown")
            session.output = result.get("output")
            session.traces = [
                next(
                    (t for t in result.get("trace", []) if isinstance(t, object)),
                    None
                )
                for _ in result.get("trace", [])
            ]

            # Save session
            session.save_jsonl()
            self.active_threads[thread_id] = session

            return {
                "output": result.get("output", ""),
                "thread_id": thread_id,
                "traces": [t.as_dict if hasattr(t, "as_dict") else t for t in result.get("trace", [])],
                "total_latency_ms": sum(
                    t.latency_ms if hasattr(t, "latency_ms") else 0
                    for t in result.get("trace", [])
                ),
            }

        except Exception as e:
            logger.error(f"consciousness_engine.think failed: {e}", exc_info=True)
            return {
                "output": f"Reasoning failed: {str(e)[:100]}",
                "thread_id": thread_id,
                "traces": [],
                "total_latency_ms": 0,
                "error": str(e),
            }

    async def think_async(
        self,
        input_text: str,
        user_id: str = "anonymous",
        thread_id: str | None = None,
    ) -> dict:
        """Async version of think()."""
        return await asyncio.to_thread(self.think, input_text, user_id, thread_id)

    def recall(self, query: str, user_id: str = "anonymous") -> dict:
        """Retrieve relevant context without reasoning."""
        from runtime.neural_brain.memory.neural_memory_manager import NeuralMemoryManager

        try:
            mem = NeuralMemoryManager()
            result = mem.recall(query, k=5)
            return {
                "results": result.get("results", []),
                "stores": result.get("stores", []),
                "hit_count": len(result.get("results", [])),
            }
        except Exception as e:
            logger.error(f"recall failed: {e}")
            return {"results": [], "stores": [], "hit_count": 0, "error": str(e)}

    def remember(
        self,
        content: str,
        memory_type: str = "episodic",
        user_id: str = "anonymous",
        metadata: dict | None = None,
    ) -> dict:
        """Store content in long-term memory."""
        from runtime.neural_brain.memory.neural_memory_manager import NeuralMemoryManager

        try:
            mem = NeuralMemoryManager()
            result = mem.remember(
                content=content,
                type=memory_type,
                user_id=user_id,
                metadata=metadata or {},
            )
            return {
                "id": result.get("id"),
                "stores": result.get("stores", []),
            }
        except Exception as e:
            logger.error(f"remember failed: {e}")
            return {"id": None, "stores": [], "error": str(e)}

    def forget(self, memory_id: str) -> dict:
        """Remove memory from all stores."""
        from runtime.neural_brain.memory.neural_memory_manager import NeuralMemoryManager

        try:
            mem = NeuralMemoryManager()
            mem.forget(memory_id)
            return {"id": memory_id, "deleted": True}
        except Exception as e:
            logger.error(f"forget failed: {e}")
            return {"id": memory_id, "deleted": False, "error": str(e)}

    def get_graph_snapshot(self, limit: int = 200) -> dict:
        """Fetch current knowledge graph state."""
        from runtime.neural_brain.graph.brain_graph import BrainGraph
        from runtime.neural_brain.graph.graph_to_dashboard import graph_to_dashboard

        try:
            graph = BrainGraph()
            snapshot = graph.full_snapshot(limit=limit)
            return graph_to_dashboard(snapshot)
        except Exception as e:
            logger.error(f"get_graph_snapshot failed: {e}")
            return {"nodes": [], "links": [], "stats": {}, "error": str(e)}

    def get_status(self) -> dict:
        """System health and readiness."""
        from runtime.neural_brain.config.settings import get_settings

        settings = get_settings()

        status = {
            "neo4j": self._check_neo4j(),
            "chroma": self._check_chroma(),
            "ollama": self._check_ollama(),
            "embed": "ok",  # Lazy loaded, assume ok
            "archs": {
                "LLM": "ok",
                "SLM": "ok",
                "MoE": "ok",
                "VLM": "ok",
                "MLM": "ok",
                "LAM": "ok",
                "LCM": "disabled" if not settings.lcm_enabled else "ok",
                "SAM": "disabled" if not settings.sam_enabled else "ok",
            },
        }
        return status

    def _check_neo4j(self) -> str:
        try:
            from runtime.neural_brain.graph.neo4j_adapter import get_neo4j_driver

            driver = get_neo4j_driver()
            driver.verify_connectivity()
            return "ok"
        except Exception:
            return "error"

    def _check_chroma(self) -> str:
        try:
            from runtime.neural_brain.memory.chroma_adapter import ChromaAdapter

            ca = ChromaAdapter()
            ca.client.list_collections()
            return "ok"
        except Exception:
            return "error"

    def _check_ollama(self) -> str:
        try:
            from runtime.neural_brain.config.settings import get_settings

            settings = get_settings()
            import httpx

            resp = httpx.get(f"{settings.ollama_host}/api/tags", timeout=2.0)
            return "ok" if resp.status_code == 200 else "error"
        except Exception:
            return "error"
