"""Canonical Neural Brain WebSocket event names.

These event names are emitted by the Python runtime via NodeBridge → Node
broadcaster → frontend WebSocket. The frontend's useWebSocket.js subscribes
to these.
"""
from __future__ import annotations

# Reasoning lifecycle (one event per LangGraph node executed)
NB_REASONING_STEP = "nb:reasoning_step"        # {trace_id, thread_id, node, msg, payload}

# Memory IO
NB_MEMORY_WRITE = "nb:memory_write"            # {id, type, user_id, preview}
NB_MEMORY_READ = "nb:memory_read"              # {query, hit_count, stores}

# Knowledge graph deltas (for the live sphere)
NB_GRAPH_UPDATE = "nb:graph_update"            # {nodes_added, links_added, node_ids}

# Model router activity (powers the 8-arch status row)
NB_MODEL_CALL = "nb:model_call"                # {arch, status, model, provider, latency_ms, error?}

# Action execution (LAM)
NB_ACTION_CALL = "nb:action_call"              # {skill, args_preview, status, latency_ms, error?}

# Thread lifecycle
NB_THREAD_CREATED = "nb:thread_created"        # {thread_id, user_id, input_preview}

# Forge / self-improvement
NB_FORGE_SUBMITTED = "nb:forge_submitted"      # {snapshot_id, goal, risk_level}
NB_FORGE_APPROVED = "nb:forge_approved"        # {snapshot_id, status}
NB_FORGE_REJECTED = "nb:forge_rejected"        # {snapshot_id, status}
NB_FORGE_DEPLOYED = "nb:forge_deployed"        # {snapshot_id, module}
NB_FORGE_BUILD_COMPLETE = "nb:forge_build_complete"  # {project_name, target_type, file_count}

# Artifact generation
NB_ARTIFACT_CREATED = "nb:artifact_created"   # {artifacts: [{name, type}]}

ALL_EVENTS = (
    NB_REASONING_STEP,
    NB_MEMORY_WRITE,
    NB_MEMORY_READ,
    NB_GRAPH_UPDATE,
    NB_MODEL_CALL,
    NB_ACTION_CALL,
    NB_THREAD_CREATED,
    NB_FORGE_SUBMITTED,
    NB_FORGE_APPROVED,
    NB_FORGE_REJECTED,
    NB_FORGE_DEPLOYED,
    NB_FORGE_BUILD_COMPLETE,
    NB_ARTIFACT_CREATED,
)
