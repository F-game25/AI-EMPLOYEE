# NEURAL OS RESEARCH — Architectural Foundation for an AI Operating System

**Document version:** 1.0.0
**Audience:** System architects, senior engineers building production AI platforms
**Status:** Reference specification — all design decisions must be justified against this document

---

## TABLE OF CONTENTS

1. How Neural Networks Actually Work
2. System-Level Intelligence Architecture
3. Humanlike Reasoning via Architecture
4. Complete Memory Architecture (14 Types)
5. RAG Pipeline Architecture
6. 14 Agent Type Definitions
7. Safe Execution Architecture — 5 Risk Levels
8. Local vs External Model Routing Logic
9. Quantisation
10. Company-Building and Money-Mode Intelligence
11. UI/Dashboard Requirements
12. Final Context Summary

---

## SECTION 1: How Neural Networks Actually Work

### 1.1 Neurons, Weights, Biases, Activation Functions

A neural network is a parameterized function. Every computation unit (neuron) computes:

```
output = activation(sum(weight_i * input_i) + bias)
```

**Weights** are real-valued scalars learned during training. **Bias** is a learned offset that shifts the activation threshold. Neither has semantic meaning individually — meaning emerges from patterns across millions of parameters.

**Activation functions** introduce non-linearity (without which stacked layers collapse to a single linear transform):

| Function | Formula | Range | Use Case | Notes |
|---|---|---|---|---|
| ReLU | max(0, x) | [0, ∞) | Hidden layers, CNNs | Fast, dying neuron problem |
| GELU | x · Φ(x) | (-∞, ∞) | Transformers (BERT, GPT) | Smooth, probabilistic gating |
| SiLU/Swish | x · σ(x) | (-∞, ∞) | LLaMA, Mistral | Non-monotonic, self-gated |
| Softmax | e^xi / Σe^xj | (0,1), sum=1 | Output layer, attention | Probability distribution |
| Sigmoid | 1/(1+e^-x) | (0, 1) | Gates, binary classification | Vanishing gradient risk |

### 1.2 Layer Types

**Dense (fully connected):** Every neuron connects to every neuron in the previous layer. Matrix multiply: `Y = XW + b`. Expensive at scale — O(n²) parameters.

**Sparse:** Only a subset of connections are active. Mixture-of-Experts (MoE) is the dominant sparse pattern in frontier models — a router selects 2 of N expert FFN layers per token, so a 70B-parameter MoE model activates ~13B parameters per forward pass.

**Layer roles:**
- **Input layer:** Receives token embeddings (or pixel values, audio frames, etc.)
- **Hidden layers:** Learn intermediate representations — lower layers capture syntax/surface features, upper layers capture semantics/reasoning
- **Output layer:** Projects to vocabulary size (LLMs) or task-specific dimensions

### 1.3 Embeddings

A tokenizer splits text into tokens (subword units). Each token maps to an integer ID. An embedding matrix `E ∈ R^(vocab_size × d_model)` converts that ID to a dense vector:

```
"bank" → token_id=4721 → E[4721] → [0.23, -1.07, 0.88, ..., 0.41]  (d_model dimensions)
```

Why embeddings capture semantics: during training, tokens that appear in similar contexts get pulled toward each other in embedding space. The famous result: `vec("king") - vec("man") + vec("woman") ≈ vec("queen")`. This is not designed — it emerges from loss minimization over billions of co-occurrences.

Embedding dimension (d_model) in production models:

| Model class | d_model | Vocab size |
|---|---|---|
| 7B dense | 4096 | 32000–128000 |
| 13B dense | 5120 | 32000–128000 |
| 70B dense | 8192 | 128000 |
| 405B dense | 16384 | 128000 |

### 1.4 Transformers: Architecture

The Transformer (Vaswani et al., 2017) is the dominant architecture for LLMs. Each layer contains:

1. **Multi-head self-attention** (MHSA)
2. **Position-wise feed-forward network** (FFN)
3. **Layer normalization** (pre-norm or post-norm)
4. **Residual connections** (skip connections that stabilize training)

```
Layer output = LayerNorm(x + FFN(LayerNorm(x + MHSA(x))))
```

**Positional encodings** inject sequence order information. Pure attention is permutation-invariant (it sees a bag of tokens), so position must be added explicitly:

- **Sinusoidal (original):** Fixed sin/cos functions of position and dimension
- **RoPE (Rotary Position Embedding):** Rotates Q/K vectors by position angle — enables length generalization beyond training context
- **ALiBi:** Adds linear bias to attention scores — simpler, good extrapolation

### 1.5 Attention Mechanism

Self-attention computes how much each token should attend to every other token in the sequence.

**Step-by-step:**

```python
# Input: X ∈ R^(seq_len × d_model)
Q = X @ W_Q   # Queries: what am I looking for?
K = X @ W_K   # Keys:    what do I offer?
V = X @ W_V   # Values:  what do I return if selected?

# Scaled dot-product attention
scores = (Q @ K.T) / sqrt(d_k)          # Scale prevents softmax saturation
scores = softmax(scores)                  # Attention weights (sum to 1 per row)
output = scores @ V                       # Weighted sum of values
```

**Multi-head attention** runs H independent attention heads in parallel, each with its own Q/K/V projections, then concatenates and projects:

```python
head_i = Attention(X @ W_Qi, X @ W_Ki, X @ W_Vi)
MHSA = concat(head_1, ..., head_H) @ W_O
```

Each head learns a different type of relationship (syntactic dependencies, coreference, positional proximity, semantic similarity). This is why multi-head attention is more powerful than single-head.

**Why attention enables long-range dependencies:** The computation between any two tokens is O(1) — direct. RNNs required information to flow through every intermediate step (O(n) path length), causing gradient vanishing. Attention eliminates this bottleneck. The cost is O(seq_len²) memory, which is why long-context models require engineering solutions (sliding window attention, flash attention, linear attention approximations).

### 1.6 Training vs Inference

**Training (forward + backward pass):**

```
forward:  input → layers → prediction → loss = CrossEntropy(prediction, target)
backward: dL/dW via backpropagation (chain rule through all layers)
update:   W = W - lr * gradient   (Adam/AdamW optimizer)
```

Training is stochastic (random batch sampling, dropout, data augmentation) and requires storing activations for the backward pass (memory-intensive).

**Inference (forward pass only):**

```
forward:  input → layers → logits → sample next token → repeat
```

Inference is deterministic given fixed weights and sampling parameters. Temperature=0 (greedy decoding) produces a fixed output. Temperature > 0 introduces controlled randomness via softmax temperature scaling.

**Key difference:** Training modifies weights. Inference reads them. A deployed model is a frozen function.

### 1.7 What Neural Networks Are and Are Not

Neural networks are **universal function approximators** (Universal Approximation Theorem). Given sufficient capacity and data, they can approximate any measurable function. This is a mathematical property, not intelligence.

What they do:
- Compress statistical regularities from training data into weights
- Interpolate and extrapolate within the distribution of training data
- Pattern-match at massive scale with learned hierarchical features

What they do NOT do:
- Maintain a world model with causal understanding
- Perform guaranteed logical deduction
- Verify their own outputs for factual correctness
- Update their knowledge after training (weights are frozen)
- "Think" in any symbolic or conscious sense

**Why architecture around the model is mandatory:** A model is a static function. It cannot search the web, remember yesterday's conversation, verify calculations, execute code, or plan multi-step workflows. All of these capabilities require external architecture: memory systems, tool executors, verification loops, planning layers, and feedback mechanisms. Bigger models improve quality within this constraint — they do not eliminate the need for architecture.

---

## SECTION 2: System-Level Intelligence Architecture

"Smart behavior" is not a property of a model — it is a property of an architecture. The components that produce intelligent system behavior:

```
USER INPUT
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  INPUT LAYER                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Tokenizer   │  │  Intent      │  │  Safety Pre-screen       │  │
│  │  + Embedding │→ │  Classifier  │→ │  (block/flag/pass)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MEMORY RETRIEVAL LAYER                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Vector RAG  │  │  Structured  │  │  Working Memory          │  │
│  │  (semantic)  │  │  DB lookup   │  │  (session context)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PLANNING LAYER                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Goal decomposition → sub-tasks → dependency graph           │   │
│  │  Resource allocation → agent selection → tool routing        │   │
│  │  Risk assessment → approval gate routing                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  EXECUTION LAYER (multi-agent)                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐  │
│  │ Research │  │ Coding   │  │ Document │  │ Tool Executor      │  │
│  │ Agent    │  │ Agent    │  │ Agent    │  │ (web/file/API/DB)  │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  VERIFICATION LAYER                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Self-check   │  │ QA Agent     │  │  Safety post-screen      │  │
│  │ (model       │  │ review       │  │  (output filter)         │  │
│  │  self-eval)  │  └──────────────┘  └──────────────────────────┘  │
│  └──────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FEEDBACK & LEARNING LAYER                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Memory      │  │  Failure     │  │  Reflection Agent        │  │
│  │  write-back  │  │  logging     │  │  (improve next run)      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
USER OUTPUT + UI UPDATE
```

**Component interdependencies:**

| Component | Depends on | Provides to |
|---|---|---|
| RAG retrieval | Vector store, embedding model | Planning, execution |
| Planning | Intent, retrieved context, memory | Execution layer |
| Execution | Plan, tools, agent pool | Verification |
| Verification | Execution output, rubrics | Feedback, user |
| Memory write-back | Verified output | Future retrieval |
| Model router | Task type, hardware state, cost policy | All LLM callers |

---

## SECTION 3: Humanlike Reasoning via Architecture

### 3.1 Goal Decomposition

Goals must be decomposed before execution. A flat goal ("build me a SaaS") cannot be executed by a single LLM call.

```python
# Decomposition pattern
def decompose(goal: str, context: dict) -> TaskGraph:
    # Phase 1: Identify goal type (research / build / analyze / communicate)
    # Phase 2: Break into 3-7 sub-tasks with dependency edges
    # Phase 3: Assign agent type per sub-task
    # Phase 4: Identify which sub-tasks can parallelize
    # Phase 5: Assign risk level per sub-task (determines approval gates)
    return TaskGraph(nodes=subtasks, edges=dependencies)
```

Sub-task sizing rule: each sub-task must be completable in a single agent turn with a verifiable output. Tasks that cannot be verified are too large.

### 3.2 Internal Chain-of-Thought (Hidden from User)

System-internal reasoning must NOT be exposed to the user in raw form. The reasoning trace is:
- Used by the planning layer to make decisions
- Logged to the audit trail (internal)
- Summarized as rationale in the response (user-facing)
- Never streamed verbatim to the UI

This prevents confusion, prompt injection via reasoning trace manipulation, and exposes a cleaner interface.

### 3.3 Working Memory (Active Context Management)

The context window is finite (e.g., 128K tokens). Working memory is the runtime management of what occupies that window:

```
Context window budget (128K tokens):
├── System prompt + agent identity:     ~2,000
├── Retrieved long-term memories:       ~8,000
├── RAG retrieved documents:           ~20,000
├── Conversation history (compressed): ~10,000
├── Current task plan:                  ~3,000
├── Tool results (current turn):       ~15,000
├── Scratchpad / intermediate output:   ~20,000
└── Reserve for response generation:   ~50,000
```

Working memory manager responsibilities:
- Evict least-relevant history when budget fills
- Compress tool results to summaries after use
- Prioritize recent + high-relevance memories
- Never evict the current task plan mid-execution

### 3.4 Persistent Memory (Cross-Session Recall)

Persistent memory stores information that survives session termination. Three storage strategies:

| Strategy | Format | Retrieval | Best for |
|---|---|---|---|
| Vector store | Embeddings + metadata | Semantic similarity search | Unstructured knowledge, documents |
| Structured DB | SQL/JSON tables | Exact query, filters | Entities, relationships, counts |
| Key-value cache | String keys → values | Exact lookup | Preferences, settings, identifiers |

Write policy: memory is written AFTER output verification, not during generation. Writing unverified content creates compounding errors.

### 3.5 Context Ranking

When multiple memories are retrieved, they must be ranked before inclusion:

```
relevance_score = (
    semantic_similarity * 0.40 +
    recency_score       * 0.25 +
    confidence_score    * 0.20 +
    importance_tag      * 0.15
)
```

Top-K by relevance_score are included in context. The rest are discarded for this turn.

### 3.6 Self-Checking

After generation, before returning output, the model runs a self-evaluation pass:

```python
self_check_prompt = f"""
Review your response against these criteria:
1. Does it directly answer the user's question?
2. Are all factual claims verifiable or appropriately hedged?
3. Is any step logically unsound?
4. Is the recommended action safe at risk level {task.risk_level}?

Output: {{"pass": true/false, "issues": [...], "confidence": 0.0-1.0}}
"""
```

If confidence < 0.7 or issues are found: revise before returning.

### 3.7 Multi-Agent Review

For high-stakes outputs, a second agent independently reviews:

```
Agent A generates output
    │
    ▼
Agent B receives:
  - Original task
  - Agent A's output
  - Review rubric (NOT Agent A's reasoning)
    │
    ▼
Agent B outputs: PASS / FAIL + critique
    │
    ▼
If FAIL: Agent A revises, or escalate to human
If PASS: Output released
```

This pattern catches systematic biases that self-checking misses (a model cannot reliably catch its own hallucinations of the same type).

### 3.8 Step-by-Step Execution with Rollback

Every execution plan is a DAG (directed acyclic graph). Each node is atomic:

```python
class TaskNode:
    id: str
    action: callable
    rollback: callable      # must be defined for Level 2+ actions
    dependencies: list[str]
    status: Literal["pending", "running", "done", "failed", "rolled_back"]
    output: Any
    error: Optional[str]
```

On failure: traverse dependency graph in reverse, call `rollback()` on each completed node. Log all rollback actions to audit trail.

### 3.9 Outcome Validation

After execution, validate that the goal was achieved, not just that the steps ran:

```python
def validate_outcome(goal: str, execution_result: dict) -> ValidationResult:
    # Structural check: did all required output fields get populated?
    # Semantic check: does the output address the original goal?
    # Constraint check: were all safety/permission constraints respected?
    # Completeness check: are all sub-tasks in DONE state?
```

### 3.10 Failure Memory and Learning

Every failure is structured and stored:

```json
{
  "failure_id": "fail-2026-05-26-0042",
  "task_type": "web_scrape",
  "goal": "extract pricing from competitor site",
  "failure_mode": "rate_limited_403",
  "attempted_recovery": "retry_with_backoff",
  "recovery_success": false,
  "root_cause": "target_site_blocks_headless_browsers",
  "recommended_fix": "use_residential_proxy_or_manual_fetch",
  "stored_at": "2026-05-26T14:33:00Z"
}
```

On next similar task: failure memory is retrieved, recommended fix applied automatically. This is the mechanism for system improvement without retraining.

### 3.11 Confidence Scoring and Uncertainty

Every model output carries a confidence estimate:

| Confidence | Behavior |
|---|---|
| 0.90–1.00 | Auto-proceed |
| 0.70–0.89 | Self-check pass → proceed |
| 0.50–0.69 | Request clarification or escalate to stronger model |
| 0.00–0.49 | Block output, escalate to human, log as uncertainty event |

Confidence is estimated via: logit entropy (for token-level), self-evaluation score, consistency across N samples (sample 3 responses, measure agreement).

### 3.12 Clarification Protocol

Clarification is expensive (it blocks execution, irritates users). Rules:

- Ask if and only if: the goal is ambiguous AND the ambiguity changes which action to take
- Never ask about things inferable from context
- Batch all clarifications into one message
- Provide suggested options — do not ask open-ended questions
- After 2 turns of back-and-forth, make a stated assumption and proceed

---

## SECTION 4: Complete Memory Architecture (14 Types)

### 4.1 Short-Term Session Memory

| Attribute | Definition |
|---|---|
| What is stored | Current conversation turns, active task state, tool results from this session |
| What is NOT stored | Cross-session data, user identity, long-term preferences |
| Retrieval | In-memory list/dict, LIFO access pattern |
| Update strategy | Append on every turn; compress after 20 turns |
| Decay | Wiped on session end |

### 4.2 Long-Term User Memory

| Attribute | Definition |
|---|---|
| What is stored | User name, communication preferences, recurring goals, stated constraints |
| What is NOT stored | Conversation transcripts verbatim, one-off task details |
| Retrieval | Key-value lookup by user_id + category |
| Update strategy | Explicit user confirmation required before write |
| Decay | Stale preferences expire after 90 days without reinforcement |

### 4.3 Project Memory

| Attribute | Definition |
|---|---|
| What is stored | Project goals, architecture decisions, open issues, file index, stakeholders |
| What is NOT stored | Deleted decisions, superseded designs |
| Retrieval | Semantic search scoped to project_id |
| Update strategy | Agent writes after task completion; user can correct |
| Decay | No decay while project is active; archive after 6 months inactive |

### 4.4 Company/Business Memory

| Attribute | Definition |
|---|---|
| What is stored | Brand voice, pricing, ICP, active offers, sales playbooks, legal constraints |
| What is NOT stored | Individual deal details (in CRM), employee PII |
| Retrieval | Structured lookup (product catalog) + semantic (brand tone) |
| Update strategy | Admin-only writes; versioned with change history |
| Decay | Price/offer data expires after 30 days if not refreshed |

### 4.5 Skill Memory

| Attribute | Definition |
|---|---|
| What is stored | Which skill × task-type combinations succeed, average completion time, error rates |
| What is NOT stored | Individual execution logs (in tool history) |
| Retrieval | Lookup by task_type → ranked skill recommendations |
| Update strategy | Automatic write-back after every skill execution (success/fail + latency) |
| Decay | Running 90-day weighted average — old data discounted |

### 4.6 Tool Execution History

| Attribute | Definition |
|---|---|
| What is stored | Tool name, inputs, outputs, latency, error, timestamp, task_id |
| What is NOT stored | Raw API keys, PII passed as inputs (redacted before store) |
| Retrieval | Query by tool name + date range; join with task_id |
| Update strategy | Append-only; immutable after write |
| Decay | Retain 30 days raw; aggregate to summaries at 90 days |

### 4.7 Research Memory

| Attribute | Definition |
|---|---|
| What is stored | Source URLs, extracted facts, confidence scores, retrieval timestamp |
| What is NOT stored | Full HTML source (only extracted content), broken/404 URLs |
| Retrieval | Semantic vector search; freshness filter (max age configurable) |
| Update strategy | Written after each research session; deduped on URL + content hash |
| Decay | Confidence decays 5% per week; re-fetch triggers reset |

### 4.8 Financial/Money-Mode Memory

| Attribute | Definition |
|---|---|
| What is stored | Revenue events, pipeline stages, approved outreach logs, ROI per workflow |
| What is NOT stored | Unapproved outreach attempts, failed payment details |
| Retrieval | Structured SQL query (aggregate by time period, workflow type) |
| Update strategy | Dual-confirm write for financial events; admin review within 24h |
| Decay | No decay; permanent audit trail required |

### 4.9 Failure Memory

| Attribute | Definition |
|---|---|
| What is stored | Failure type, task context, attempted recovery, root cause, recommended fix |
| What is NOT stored | Duplicate failures (deduplicated by error_signature hash) |
| Retrieval | Lookup by task_type + error_signature before execution |
| Update strategy | Auto-written on any task failure; human can annotate root cause |
| Decay | Failures resolved by successful pattern retained as "resolved" for 1 year |

### 4.10 Decision Memory

| Attribute | Definition |
|---|---|
| What is stored | Decision taken, options considered, rationale, who approved, timestamp |
| What is NOT stored | Speculative reasoning, rejected options in full detail |
| Retrieval | Query by task domain + time range |
| Update strategy | Written at decision point; immutable |
| Decay | None — decision provenance is permanent |

### 4.11 Preference Memory

| Attribute | Definition |
|---|---|
| What is stored | Output format preferences, verbosity level, domain-specific style rules |
| What is NOT stored | Inferred preferences without confirmation (speculation is not preference) |
| Retrieval | Key lookup: user_id → preference_category → value |
| Update strategy | Explicit user statement triggers update; agent may propose, user confirms |
| Decay | Preferences unreferenced for 60 days flagged for review |

### 4.12 Vector/RAG Memory

| Attribute | Definition |
|---|---|
| What is stored | Chunked text + embedding vectors + source metadata + permission scope |
| What is NOT stored | Binary files, images (unless captioned), encrypted content |
| Retrieval | ANN (approximate nearest neighbor) vector search; optional keyword filter |
| Update strategy | Incremental — new documents ingested without full re-index |
| Decay | Freshness metadata tracked; stale chunks deprioritized in reranking |

### 4.13 Structured Database Memory

| Attribute | Definition |
|---|---|
| What is stored | Entities (users, deals, contacts, tasks), relationships, aggregates |
| What is NOT stored | Freeform text (stored in vector memory instead) |
| Retrieval | SQL/GraphQL — exact, filtered, aggregated |
| Update strategy | ACID transactions; audit-logged writes |
| Decay | Soft deletes only; hard purge requires compliance review |

### 4.14 Event Timeline Memory + Knowledge Graph Memory

**Event Timeline:**

| Attribute | Definition |
|---|---|
| What is stored | Timestamped events: task start/end, approvals, failures, external triggers |
| Retrieval | Time-range query; join with task_id |
| Update strategy | Append-only event stream |
| Decay | Retain 1 year; archive to cold storage beyond |

**Knowledge Graph:**

| Attribute | Definition |
|---|---|
| What is stored | Nodes (entities) and edges (relationships) with typed labels and confidence weights |
| What is NOT stored | Speculative edges without evidence |
| Retrieval | Graph traversal (Cypher/SPARQL); pattern matching |
| Update strategy | Confidence-weighted merge — new evidence updates edge weights |
| Decay | Edges decay 2% per month without reinforcing evidence |

---

## SECTION 5: RAG Pipeline Architecture

### 5.1 Full Pipeline

```
RAW DOCUMENTS
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  INGESTION                                          │
│  PDF → pdfminer/pypdf2                              │
│  HTML → trafilatura (content extraction)            │
│  Markdown → direct parse                            │
│  Code → tree-sitter AST-aware splitting             │
│  Output: clean text + metadata (source, date, type) │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  CHUNKING                                           │
│  Target size: 512 tokens                            │
│  Overlap: 51 tokens (~10%)                          │
│  Strategy: semantic splitting preferred over fixed  │
│    - Split on paragraph/section boundaries first    │
│    - Hard split at 512 token max                    │
│    - Preserve code blocks intact (no mid-block cut) │
│    - Attach: chunk_id, doc_id, position, heading    │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  EMBEDDING                                          │
│  Local (private data): sentence-transformers        │
│    all-MiniLM-L6-v2 (fast, 384-dim)                │
│    bge-large-en-v1.5 (higher quality, 1024-dim)    │
│  API (non-sensitive): text-embedding-3-large        │
│  Batch size: 64 chunks per inference call           │
│  Store: vector + metadata in Chroma/Qdrant/pgvector │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  RETRIEVAL (HYBRID)                                 │
│  Vector search: top-20 by cosine similarity         │
│  BM25 keyword search: top-20 by TF-IDF score        │
│  Score fusion: Reciprocal Rank Fusion (RRF)         │
│    combined_score = 1/(k+rank_vector) +             │
│                     1/(k+rank_bm25)  [k=60]         │
│  Select top-40 combined candidates                  │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  RERANKING                                          │
│  Cross-encoder model (e.g., ms-marco-MiniLM-L-6-v2)│
│  Scores each (query, chunk) pair independently      │
│  Reduces 40 candidates to top-10                    │
│  WHY: bi-encoder embedding cannot capture fine-     │
│       grained query-chunk interaction; cross-encoder│
│       sees both together → 10-15% precision gain    │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  CONTEXT COMPRESSION                                │
│  Remove: chunks that repeat information already in  │
│          higher-ranked chunk (cosine similarity >   │
│          0.92 between chunks → discard lower-ranked)│
│  Summarize: chunks > 400 tokens that score below    │
│             0.75 rerank score (compress, keep cite) │
│  Result: 3-8 chunks, max 4000 tokens total          │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  CONTEXT INJECTION + CITATION                       │
│  Format:                                            │
│    [SOURCE: {doc_title}, {date}, chunk {n}]         │
│    {chunk_content}                                  │
│  Injected before user query in system prompt        │
│  Model instructed to cite [SOURCE: X] in response  │
└─────────────────────────────────────────────────────┘
    │
    ▼
LLM RESPONSE WITH CITATIONS
```

### 5.2 Design Decisions Table

| Decision | Choice | Rationale |
|---|---|---|
| Chunk size | 512 tokens | Balances specificity (small) vs context (large); benchmark sweet spot |
| Overlap | 10% | Prevents information loss at boundaries without excessive duplication |
| Hybrid search | BM25 + vector | Vector excels at semantic; BM25 at exact entity names, codes, jargon |
| Fusion | RRF | Parameter-free, rank-based — more robust than score normalization |
| Reranking | Cross-encoder | 10-15% MAP gain over vector-only; cost justified for top-K precision |
| Freshness decay | 5%/week | Prevents stale knowledge from ranking above recent without full re-index |
| Permission scope | Embedded in metadata | Retrieval filter by project_id/user_id prevents cross-tenant leakage |
| Deduplication | Content hash | Catches identical documents ingested via multiple paths |

---

## SECTION 6: 14 Agent Type Definitions

### 6.1 Orchestrator Agent

| Attribute | Definition |
|---|---|
| Purpose | Understand intent, decompose goals, route to specialist agents, manage workflow |
| Inputs | User message, session context, memory index, system state |
| Outputs | TaskGraph (sub-tasks with dependencies), agent assignments, approval gate specs |
| Tools allowed | Memory read, agent spawn, task status query — NO execution tools |
| Memory access | All memory types (read); session memory (read/write) |
| Execution permissions | Level 0 only — the orchestrator never executes external actions |
| Failure modes | Decomposition loops, infinite sub-task expansion, incorrect agent routing |
| UI visibility | Task plan displayed; agent assignments shown; real-time progress tree |

### 6.2 Research Agent

| Attribute | Definition |
|---|---|
| Purpose | Gather information from web, documents, and knowledge base to fill context gaps |
| Inputs | Research query, source constraints, freshness requirements, budget (pages/tokens) |
| Outputs | Structured research report: facts + sources + confidence scores |
| Tools allowed | Web search, browser fetch (stealth), vector store write, URL validator |
| Memory access | Research memory (read/write); vector RAG (write) |
| Execution permissions | Level 0-1 (read web, write local research store) |
| Failure modes | Rate-limiting, hallucinated citations, scope drift (researching beyond goal) |
| UI visibility | Active sources panel; live status; budget consumption bar |

### 6.3 Planning Agent

| Attribute | Definition |
|---|---|
| Purpose | Convert high-level goals into executable step-by-step plans with rollback paths |
| Inputs | Goal, decomposed sub-tasks, available tools, risk constraints |
| Outputs | Ordered execution plan with: steps, tool calls, rollback handlers, checkpoints |
| Tools allowed | Read task definitions, read tool registry, read failure memory |
| Memory access | Failure memory, decision memory, skill memory (all read) |
| Execution permissions | Level 0 only |
| Failure modes | Over-planning (too many steps), under-planning (missing dependencies), ignoring rollback |
| UI visibility | Plan preview before execution; step-by-step progress during execution |

### 6.4 Execution Agent

| Attribute | Definition |
|---|---|
| Purpose | Execute tool calls within approved plans; manage retries; report results |
| Inputs | Execution plan step, tool parameters, risk level, approval status |
| Outputs | Tool execution results, success/fail status, timing metadata |
| Tools allowed | File I/O, shell (sandboxed), API calls (approved), database writes |
| Memory access | Tool execution history (write); session memory (read/write) |
| Execution permissions | Level 1-3 based on tool and approval state |
| Failure modes | Timeout, API errors, permission denied, partial completion without rollback |
| UI visibility | Execution status per step; tool call details (collapsed by default) |

### 6.5 Coding Agent

| Attribute | Definition |
|---|---|
| Purpose | Generate, review, debug, test, and refactor code |
| Inputs | Task specification, existing codebase context, language/framework constraints |
| Outputs | Code files, test files, diff patches, explanations |
| Tools allowed | File read/write, code execution (sandboxed), linter, test runner, git |
| Memory access | Project memory (read); skill memory (read); execution history (read) |
| Execution permissions | Level 1 (create files), Level 2 (run tests), Level 3 (deploy with approval) |
| Failure modes | Compilation errors, test failures, incorrect logic, unsafe code generation |
| UI visibility | Code diff preview; test results; confidence score per file |

### 6.6 UI Agent

| Attribute | Definition |
|---|---|
| Purpose | Generate and modify frontend components, layouts, styles, and interactions |
| Inputs | UI specification, existing component library, design tokens, user feedback |
| Outputs | React/HTML/CSS components, design system updates |
| Tools allowed | File read/write, browser preview (headless), screenshot diff |
| Memory access | Project memory, preference memory (read) |
| Execution permissions | Level 1-2 |
| Failure modes | Breaking existing layout, ignoring design system, accessibility violations |
| UI visibility | Preview pane for generated components; before/after diff |

### 6.7 Business/Money Agent

| Attribute | Definition |
|---|---|
| Purpose | Execute revenue workflows: content creation, lead management, proposals, invoicing |
| Inputs | Business goal, approved contact list, offer details, brand constraints |
| Outputs | Content drafts, outreach messages (pending approval), proposals, revenue reports |
| Tools allowed | CRM read/write, content generators, email draft (NOT send — requires approval) |
| Memory access | Business memory, financial memory, preference memory |
| Execution permissions | Level 1 (draft), Level 4 (send/charge — always dual-confirm) |
| Failure modes | ToS violations, spam pattern detection, unchecked outreach, financial errors |
| UI visibility | All drafts visible before approval; pipeline stages; revenue dashboard |

### 6.8 Safety/Compliance Agent

| Attribute | Definition |
|---|---|
| Purpose | Screen all inputs and outputs for safety violations, legal risk, PII, ToS breaches |
| Inputs | Any content passing through the system (pre- and post-generation) |
| Outputs | PASS / BLOCK / FLAG + violation category + recommended action |
| Tools allowed | Content classifier, PII detector, ToS rule engine — read-only |
| Memory access | Business memory (read); decision memory (write for blocks) |
| Execution permissions | Level 0 (analysis only); can BLOCK other agents' actions |
| Failure modes | False positives blocking legitimate actions; false negatives passing unsafe content |
| UI visibility | Compliance status badge on all outputs; block audit log |

### 6.9 Memory Agent

| Attribute | Definition |
|---|---|
| Purpose | Manage all memory types: write new memories, deduplicate, decay stale, retrieve on demand |
| Inputs | Content to store, retrieval query, memory management commands |
| Outputs | Retrieved context, confirmation of write, compaction report |
| Tools allowed | Vector store, key-value store, SQL database, embedding model |
| Memory access | All 14 memory types (full read/write) |
| Execution permissions | Level 1 (local stores) |
| Failure modes | Memory bloat, duplicate storage, incorrect decay of important memories |
| UI visibility | Memory activity panel: recent reads/writes, store sizes |

### 6.10 Tool-Routing Agent

| Attribute | Definition |
|---|---|
| Purpose | Select the optimal tool for each atomic action based on capability, cost, and availability |
| Inputs | Action specification, tool registry, current tool availability, budget constraints |
| Outputs | Tool selection + configuration + fallback tool if primary unavailable |
| Tools allowed | Tool registry read, tool health check |
| Memory access | Skill memory, tool execution history (read) |
| Execution permissions | Level 0 |
| Failure modes | Selecting unavailable tools, ignoring cost constraints, no fallback |
| UI visibility | Model routing panel showing which tool used and why |

### 6.11 Verification/QA Agent

| Attribute | Definition |
|---|---|
| Purpose | Independently verify that execution output meets task requirements |
| Inputs | Original task spec, execution output, verification rubric |
| Outputs | PASS / FAIL + issues list + confidence score |
| Tools allowed | Code runner (read-only), diff tool, assertion checker |
| Memory access | Project memory (read); failure memory (write on fail) |
| Execution permissions | Level 0-1 |
| Failure modes | Missing edge cases, systematic blind spots matching the generating agent's biases |
| UI visibility | QA results panel; issue list with severity |

### 6.12 Reflection/Improvement Agent

| Attribute | Definition |
|---|---|
| Purpose | Analyze completed workflows for efficiency and quality improvements; update playbooks |
| Inputs | Completed task history, failure logs, user feedback, performance metrics |
| Outputs | Improvement recommendations, updated skill memory, playbook patches |
| Tools allowed | Memory read, memory write (improvement notes), metric query |
| Memory access | All memory types (read); skill memory, failure memory (write) |
| Execution permissions | Level 0-1 |
| Failure modes | Over-fitting to recent failures, ignoring successful patterns, producing unactionable advice |
| UI visibility | Weekly improvement report; playbook change log |

### 6.13 Document/Content Agent

| Attribute | Definition |
|---|---|
| Purpose | Generate, edit, format, and manage documents, reports, and long-form content |
| Inputs | Content brief, brand guidelines, existing documents for reference |
| Outputs | Structured documents (markdown, PDF, HTML), content edits, summaries |
| Tools allowed | File read/write, template engine, PDF renderer |
| Memory access | Project memory, business memory, preference memory (read) |
| Execution permissions | Level 1 |
| Failure modes | Brand voice drift, missing required sections, citation errors |
| UI visibility | Document preview panel; revision history |

### 6.14 Data-Analysis Agent

| Attribute | Definition |
|---|---|
| Purpose | Query, aggregate, visualize, and interpret structured data |
| Inputs | Data source (CSV, SQL, API), analysis goal, output format |
| Outputs | Statistical summaries, visualizations, interpretive narrative, anomaly flags |
| Tools allowed | SQL client, pandas/polars, charting library, stats functions |
| Memory access | Financial memory (read); project memory (read) |
| Execution permissions | Level 0-1 (read data); Level 2 (write output files) |
| Failure modes | Misleading aggregations, incorrect statistics, wrong join keys, correlation/causation confusion |
| UI visibility | Chart display; data table; methodology summary |

---

## SECTION 7: Safe Execution Architecture — 5 Risk Levels

### 7.1 Risk Level Definitions

| Level | Name | Action Types | Approval Required | Logging | Reversible Check |
|---|---|---|---|---|---|
| 0 | Read-only analysis | Query, inspect, classify, search | None | Optional | N/A (no mutation) |
| 1 | Local draft/create | Create files, draft content, write to local store | None | Required | Recommended |
| 2 | User-approved local execution | Run code, execute scripts, delete local files | UI approval (single) | Required | Required |
| 3 | External API/browser execution | Send API request, browser automation, read external data | UI approval + confirmation | Required + audit | Required |
| 4 | Financial/public-facing actions | Send emails, charge payments, publish content, post publicly | Dual-confirm + admin review | Required + audit + 24h review | Mandatory |
| 5 | Blocked actions | Illegal actions, deceptive content, destructive system commands | Never allowed | Alert logged | N/A |

### 7.2 Tool Registry

| Tool | Risk Level | Reversible | Requires Approval | Sandboxed |
|---|---|---|---|---|
| vector_search | 0 | N/A | No | Yes |
| web_search | 0 | N/A | No | Yes |
| read_file | 0 | N/A | No | Yes |
| classify_text | 0 | N/A | No | Yes |
| write_file (local) | 1 | Yes (delete) | No | Yes |
| create_draft | 1 | Yes (discard) | No | Yes |
| memory_write | 1 | Partial | No | Yes |
| run_code (sandbox) | 2 | Partial | Yes | Yes (container) |
| delete_file | 2 | No | Yes | Yes |
| git_commit | 2 | Yes (revert) | Yes | No |
| http_request (GET) | 2 | Yes (no side effect) | Yes | No |
| http_request (POST) | 3 | No | Yes | No |
| browser_fetch | 3 | N/A | Yes | Partial |
| send_email | 4 | No | Dual-confirm | No |
| crm_write | 4 | Partial | Yes | No |
| publish_content | 4 | Partial | Dual-confirm | No |
| charge_payment | 4 | No | Dual-confirm + admin | No |
| mass_outreach | 5 | No | BLOCKED | N/A |
| impersonation | 5 | N/A | BLOCKED | N/A |
| system_destruction | 5 | No | BLOCKED | N/A |

### 7.3 Approval Gate Flow

```
Task reaches risk Level 2+
    │
    ▼
System generates approval card:
  - Action description (plain English)
  - Risk level + rationale
  - Reversibility status
  - Expected outcome
  - Rollback plan
    │
    ▼
UI presents approval card to user
    │
    ├── User APPROVES → execute → log → proceed
    │
    ├── User REJECTS → log rejection → halt task → notify orchestrator
    │
    └── Timeout (60s) → auto-reject → log → notify user
```

---

## SECTION 8: Local vs External Model Routing Logic

### 8.1 Decision Matrix

| Factor | Local model | External API |
|---|---|---|
| Data privacy | Required for PII, proprietary data | Only for non-sensitive |
| Cost | Fixed (hardware) | Per-token — expensive at scale |
| Latency | Low (no network) | 100-3000ms round-trip |
| Capability ceiling | Limited by VRAM | Frontier models available |
| Offline availability | Full | Requires connectivity |
| Vision/multimodal | Model-dependent | GPT-4o, Claude 3.5 available |
| Code generation quality | Good (Qwen2.5-Coder) | Best (Claude 3.5 Sonnet) |
| Reasoning depth | Good up to 70B | Best at frontier scale |
| Hardware load | VRAM + CPU/GPU | Offloaded to API |

### 8.2 Task × Routing Decision

| Task type | Preferred route | Escalation trigger |
|---|---|---|
| Classification, intent | Local (7B) | None — 7B sufficient |
| Summarization | Local (7B-13B) | Very long documents |
| Embedding | Local (sentence-transformers) | Never API |
| Simple Q&A | Local (13B) | confidence < 0.7 |
| Complex reasoning | Local (70B) or API | Local fails, or VRAM insufficient |
| Code generation | Local (Qwen2.5-Coder-32B) | Complex architecture design |
| Safety screening | Local (fine-tuned classifier) | Never API (PII risk) |
| Reranking | Local (cross-encoder) | Never API |
| Creative writing | API preferred | Offline mode: local |

### 8.3 Routing Pseudocode

```python
def route_to_model(task: Task, system_state: SystemState) -> ModelEndpoint:
    # Privacy gate — always first
    if task.contains_pii or task.data_sensitivity == "high":
        return select_local_model(task)

    # Offline mode
    if not system_state.has_network:
        return select_local_model(task)

    # Hardware gate
    required_vram = estimate_vram(task.complexity)
    if required_vram > system_state.available_vram:
        if system_state.has_network and not task.contains_pii:
            return select_api_model(task)
        else:
            return select_quantised_local_model(task)  # degraded but available

    # Cost gate
    if system_state.api_budget_exhausted:
        return select_local_model(task)

    # Confidence escalation
    if task.previous_attempt and task.previous_attempt.confidence < 0.60:
        return escalate_to_larger_model(task)

    # User preference override
    if user_settings.force_local:
        return select_local_model(task)

    # Default routing by complexity
    if task.complexity_score < 0.3:
        return LOCAL_7B
    elif task.complexity_score < 0.6:
        return LOCAL_13B_OR_32B
    elif task.complexity_score < 0.85:
        return LOCAL_70B_OR_API_MEDIUM
    else:
        return API_FRONTIER  # Claude Opus / GPT-4o
```

### 8.4 Model Catalogue Reference

| Model | Size | VRAM | Best for | Privacy-safe |
|---|---|---|---|---|
| Qwen2.5-0.5B | 0.5B | 1GB | Fast classification | Yes |
| Phi-3-mini | 3.8B | 3GB | Light reasoning | Yes |
| Llama-3.2-8B | 8B | 6GB | General tasks | Yes |
| Qwen2.5-Coder-32B | 32B | 20GB | Code generation | Yes |
| Llama-3.3-70B | 70B | 40GB | Complex reasoning | Yes |
| Claude 3.5 Haiku | API | 0 | Fast API tasks | No (external) |
| Claude 3.5 Sonnet | API | 0 | Best balance | No (external) |
| Claude 3 Opus | API | 0 | Frontier reasoning | No (external) |

---

## SECTION 9: Quantisation

### 9.1 Why Quantisation Matters

A 70B parameter model in FP32 requires ~280GB VRAM. No consumer or prosumer GPU handles this. Quantisation reduces precision of stored weights, dramatically cutting memory footprint with acceptable quality loss.

### 9.2 Precision Formats

| Format | Bits/param | 7B VRAM | 70B VRAM | Quality | Speed | Use case |
|---|---|---|---|---|---|---|
| FP32 | 32 | 28GB | 280GB | Reference | Slowest | Training only |
| FP16/BF16 | 16 | 14GB | 140GB | ~FP32 | Fast | Fine-tuning, high-value inference |
| INT8 | 8 | 7GB | 70GB | 98% of FP16 | Faster | Production inference (capable GPU) |
| INT4 (Q4_K_M) | 4 | 4GB | 35GB | 95% of FP16 | Fastest local | Edge, fast response, private tasks |
| INT2 | 2 | 2GB | 17GB | 85-90% of FP16 | Very fast | Classification, embeddings only |

Q4_K_M (4-bit, K-quantisation, Medium) is the current practical sweet spot — it fits a 7B model on a 4GB GPU with negligible quality loss for general tasks.

### 9.3 When to Use Quantised Models

**Use quantised (INT4/INT8) for:**
- Fast classification and intent detection
- Summarization of long documents
- RAG answer synthesis (retrieval compensates for model quality)
- Code completion (syntax correctness > reasoning depth)
- Private/local tasks where API cannot be used
- High-throughput, low-latency applications
- Edge deployment (laptop, embedded)

### 9.4 When NOT to Use Quantised Models

**Avoid quantised for:**
- Critical multi-step reasoning (math, logic proofs)
- Complex code architecture generation
- Compliance and legal document review
- Medical or safety-critical analysis
- Tasks where 3-5% quality degradation has material consequences
- Fine-tuning (always use FP16 minimum)

### 9.5 Hardware Detection and Auto-Selection

```python
def auto_select_precision(model_params_B: float) -> ModelConfig:
    vram_gb = get_available_vram_gb()
    
    # Size requirements at each precision (rough GB = params_B * bytes_per_param)
    fp16_gb  = model_params_B * 2.0
    int8_gb  = model_params_B * 1.0
    int4_gb  = model_params_B * 0.5
    
    safety_margin = 0.85  # use 85% of VRAM max to avoid OOM
    usable_vram = vram_gb * safety_margin
    
    if usable_vram >= fp16_gb:
        return ModelConfig(precision="fp16", quality="full")
    elif usable_vram >= int8_gb:
        return ModelConfig(precision="int8", quality="high")
    elif usable_vram >= int4_gb:
        return ModelConfig(precision="int4", quality="good")
    else:
        return ModelConfig(model="api", reason="insufficient_vram")
```

### 9.6 Keeping the UI Responsive During Model Loading

Local models take 2-30 seconds to load. The UI must remain interactive:

```
Model load initiated
    │
    ├── WebSocket event: {"type": "model:loading", "model": "Llama-70B-Q4", "progress": 0}
    │
    ├── Loading thread streams progress every 500ms:
    │     {"type": "model:loading", "progress": 0.45, "layers_loaded": 32, "total": 80}
    │
    ├── UI shows loading bar in "Brain Status" panel
    │   User can queue tasks — they execute after model ready
    │
    └── On complete: {"type": "model:ready", "model": "Llama-70B-Q4", "load_time_ms": 8400}
```

---

## SECTION 10: Company-Building and Money-Mode Intelligence

### 10.1 Revenue Workflow Architecture

```
NICHE RESEARCH
  ├── Market sizing: search + aggregate + estimate TAM
  ├── Competitor analysis: identify gaps, pricing, positioning
  └── ICP definition: demographic + psychographic + problem profile
    │
    ▼
OFFER CREATION
  ├── Service/product definition grounded in ICP pain
  ├── Pricing model (productized service / SaaS / consulting)
  └── Value proposition: outcome-focused, quantified
    │
    ▼
CONTENT & LANDING PAGE
  ├── Long-form content: SEO-targeted, ICP-aligned
  ├── Landing page: headline → problem → solution → proof → CTA
  └── All content human-reviewed before publish
    │
    ▼
OUTREACH (human-approved per item)
  ├── Lead identification: public directories, LinkedIn (within ToS)
  ├── Message draft: personalized, not templated
  └── HITL gate: each message requires individual human approval before send
    │
    ▼
LEAD MANAGEMENT
  ├── CRM pipeline: prospect → qualified → proposal → closed
  ├── Follow-up sequences: drafted by agent, approved by human
  └── Qualification scoring: based on ICP fit, not volume
    │
    ▼
DELIVERY & INVOICING
  ├── Proposal generation: SOW + timeline + pricing
  ├── Project tracking: milestone-based
  └── Invoice: generated + human-approved before send
    │
    ▼
ROI TRACKING & PLAYBOOK
  ├── Revenue per workflow tracked
  ├── Conversion rates at each stage
  └── Winning playbooks stored in business memory for reuse
```

### 10.2 Safety Rules (Non-Negotiable)

| Rule | Enforcement mechanism |
|---|---|
| No mass outreach without per-item approval | HITL gate blocks all send actions; batch send is blocked at Level 5 |
| No deceptive content | Safety agent pre-screens all outreach; deception classifier blocks at 0.7+ score |
| No impersonation | Safety agent checks sender identity matches authenticated user |
| No fake reviews or testimonials | Content classifier; explicit training signal in safety model |
| No GDPR/CAN-SPAM violations | Compliance ruleset checked before any email draft |
| No platform ToS violations | ToS ruleset per platform; actions blocked if rule match found |
| Financial actions dual-confirm | All Level 4 financial actions require two separate UI confirmations |
| Reversibility check before financial action | System checks if action is reversible; if not, extra warning shown |

---

## SECTION 11: UI/Dashboard Requirements

### 11.1 Brain/Core Status Panel

**Data required:** active model name, precision, VRAM used, current pipeline phase, last action timestamp, system confidence score, active agent count

**Must display:**
- Active model: "Llama-3.3-70B (INT4) — 34GB / 40GB VRAM"
- Pipeline phase: e.g., "Phase 4: call_llm — in progress"
- System confidence: percentage with color coding (green/amber/red)
- Last completed action: plain-English description + timestamp
- Processing indicator: real-time token/s rate while generating

### 11.2 Agent Activity Panel

**Data required:** agent registry, current task assignments, task queue length, completion rate, per-agent error count

**Must display:**
- Active agents list with status badge (idle / running / waiting / error)
- Current task per agent: task description + elapsed time
- Task queue: ordered list of pending tasks with risk level badge
- Completion rate: 7-day rolling (tasks completed / tasks attempted)
- Error log: last 10 agent errors with agent ID, error type, task context

### 11.3 Memory Activity Panel

**Data required:** read/write event stream, store sizes (by memory type), last retrieval queries, write timestamps

**Must display:**
- Live feed: "Memory write: project memory — architecture decision logged"
- Store sizes: table of 14 memory types with row count and storage size
- Last retrieval: query + number of results + latency
- Memory health: alert if any store exceeds growth threshold (configurable)

### 11.4 RAG Sources Panel

**Data required:** indexed document list, last retrieval event, source quality scores, freshness dates

**Must display:**
- Indexed document count + total chunk count
- Last retrieval: query snippet + sources used + rerank scores
- Source health: freshness status per document (fresh / stale / expired)
- Failed ingestion log: documents that could not be indexed + reason

### 11.5 Model Routing Decisions Panel

**Data required:** routing log with decision reason, model used, task type, cost, latency

**Must display:**
- Recent routing decisions table: task → model → reason → latency → cost
- Cost tracker: API spend per day with budget bar
- Local vs API ratio: pie chart (7-day rolling)
- Escalations: tasks that escalated from local to API due to low confidence

### 11.6 Execution Queue Panel

**Data required:** pending tasks with risk level, approval gate status, task dependencies

**Must display:**
- Queue list: task description + risk level badge + status (pending approval / running / blocked)
- Approval cards: expandable cards for Level 2+ tasks requiring human approval
- Blocked tasks: tasks blocked by dependency or approval — reason displayed
- Rollback controls: for in-progress Level 2+ tasks, one-click rollback button

### 11.7 Research Workspace Panel

**Data required:** active research sessions, sources visited, knowledge extracted, budget consumed

**Must display:**
- Active research: goal + hops completed + sources visited + budget remaining
- Source list: URL + quality score + extraction status
- Extracted knowledge preview: last 5 facts added to research memory
- Historical sessions: completed research with date + goal + sources count

### 11.8 Money Mode Panel

**Data required:** active workflows, pipeline stages, pending approvals, revenue events

**Must display:**
- Active workflows: type + stage + next action + assignee
- Pending approvals: outreach messages / proposals awaiting human review
- Pipeline: Kanban or table with deal stages and values
- Revenue: this month total + pipeline value + conversion rate

### 11.9 Logs/Audit Panel

**Data required:** all Level 2+ action records with timestamp, user, action, outcome, tool used

**Must display:**
- Chronological audit log: timestamp | user | action | tool | risk level | outcome
- Filter: by risk level, agent, date range, outcome (success/fail/blocked)
- Export: CSV download for compliance review
- Block log: all Level 5 blocks with reason and flagged content (redacted for display)

### 11.10 System Health Panel

**Data required:** CPU, RAM, VRAM usage; per-route latency; error rate; uptime

**Must display:**
- Resource gauges: CPU %, RAM GB, VRAM GB — color-coded (green/amber/red)
- Request latency: p50/p95/p99 per API route — updated every 30s
- Error rate: errors per minute with 15-minute trend
- Uptime: since last restart + version info
- Active connections: WebSocket count + REST request rate

---

## SECTION 12: Final Context Summary

### What This System Must Become

A production-grade AI operating layer — not a chatbot wrapper, not a demo, not a collection of scripts. The system is an autonomous execution engine that combines models, memory, retrieval, planning, multi-agent coordination, tool execution, safety enforcement, and user-facing observability into a single coherent platform.

The goal is precisely stated in the architecture spec: **Convert intent → structured workflow → real-world outcome.**

### Core Architectural Principles (Non-Negotiable)

| Principle | What it means in practice |
|---|---|
| Architecture over model size | Intelligence is an emergent property of memory + retrieval + planning + verification, not model scale alone |
| Every action has a risk level | No tool call executes without being classified; Level 2+ always requires human visibility |
| Memory is first-class infrastructure | All 14 memory types are independently managed, independently retrievable, independently decaying |
| Verification is not optional | Every significant output passes through a verification step before being returned or acted upon |
| The orchestrator never executes | Orchestrator = planner + router only; execution agents hold all tool permissions |
| Failure memory drives improvement | Failures are structured data, not errors to be discarded; they feed the planning layer on next run |
| Privacy gates before everything else | PII and sensitive data must be identified before routing — never sent to external APIs |
| The UI is a control surface, not a display | Every dashboard panel must expose controls (approve, reject, rollback, cancel) not just status |
| Reversibility is a design constraint | Every Level 2+ action must have a defined rollback path or be explicitly flagged as irreversible |
| No unsafe action is accessible | Level 5 actions are blocked at the tool registry level — not by policy alone, by code |

### The Execution Model in One Diagram

```
INTENT → [ORCHESTRATOR] → PLAN → [AGENTS] → TOOLS → OUTPUT
              │                      │                  │
          MEMORY ←─────────────── VERIFY ──────────→ AUDIT
              │                      │
           FEEDBACK ←─────────── REFLECT
```

### What Must Never Happen

- Orchestrator directly calling external tools (bypasses risk classification)
- Tool calls at Level 2+ without UI visibility (silent execution)
- Memory writes of unverified content (compounds hallucination)
- External API calls with PII (privacy violation)
- Financial actions without dual-confirm (uncontrolled spend)
- Agents spawning unbounded sub-agents (resource exhaustion)
- Failure silently swallowed (no audit trail, no recovery path)
- One tenant's data accessible to another tenant's agents (isolation breach)

### Minimum Viable Production Checklist

Before any version goes to production, verify:

- [ ] All 14 memory types have working read/write/decay implementations
- [ ] RAG pipeline produces cited, deduplicated, freshness-checked results
- [ ] All 14 agent types have defined tool permissions in the tool registry
- [ ] Risk level classification runs on every tool call before execution
- [ ] Level 2+ approval gates are functional in the UI
- [ ] Audit log captures all Level 2+ actions with full metadata
- [ ] Model router selects local model for any PII-containing task
- [ ] Tenant isolation prevents cross-tenant memory access
- [ ] HITL gate blocks all financial/outreach actions without approval
- [ ] System health panel shows real-time VRAM, CPU, error rate
- [ ] Rollback handlers are defined for all Level 2+ tool calls
- [ ] Safety agent screens both inputs and outputs
- [ ] Confidence scoring is present on all model outputs
- [ ] Failure memory is written for every task failure
- [ ] WebSocket delivers live status updates to all active dashboard panels

---

*Document: NEURAL_OS_RESEARCH.md | Version 1.0.0 | Date: 2026-05-26*
*Author: Whitepaper Author Agent — AI-EMPLOYEE system*
*Audience: system architects and senior engineers*
*Status: production reference specification*
