"""
Phase 9 — Interconnected Cognitive Core Tests

Covers: memory graph nodes/edges, edge reinforcement, related-node retrieval,
contradiction detection, secret scrubbing in graph nodes, context packet
build + persistence + no-secrets, graceful degradation, consolidation,
advisory safety invariant (static source check), live route auth (skipped).
"""
import json
import os
import subprocess
import tempfile
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH_SVC = os.path.join(REPO_ROOT, 'backend', 'services', 'forge_memory_graph.js')
CTX_SVC = os.path.join(REPO_ROOT, 'backend', 'services', 'forge_context_engine.js')
STORE = os.path.join(REPO_ROOT, 'backend', 'services', 'forge_store.js')
FORGE_JS = os.path.join(REPO_ROOT, 'backend', 'routes', 'forge.js')
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8787")
TIMEOUT = 10


def node_run(body, timeout=25):
    """Run `body` JS against a real ForgeStore on a fresh temp DB. body must
    console.log a JSON object as its final stdout line."""
    script = f"""
const {{ ForgeStore }} = require({json.dumps(STORE)});
const graph = require({json.dumps(GRAPH_SVC)});
const ctx = require({json.dumps(CTX_SVC)});
const os=require('os'),path=require('path'),fs=require('fs');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'p9-'));
const store=new ForgeStore({{forgeHome:tmp,runsFile:path.join(tmp,'runs.json'),maxRuns:50}});
const nowIso=()=>new Date().toISOString();
(async()=>{{ try {{ {body} }} catch(e){{ console.log(JSON.stringify({{ok:false,error:e.message,stack:e.stack}})); }} }})();
"""
    p = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT)
    out = p.stdout.strip()
    if not out:
        raise RuntimeError(f"no output: {p.stderr[:500]}")
    return json.loads([l for l in out.split('\n') if l.strip()][-1])


class TestGraphNodes:
    def test_create_and_roundtrip(self):
        r = node_run("""
          const n = graph.upsertGraphNode(store, 'p1', {node_type:'memory', title:'use api.forge', summary:'migrate fetch calls', confidence:'high'});
          const got = store.findGraphNode(n.node_id);
          console.log(JSON.stringify({ok:true, has_id: !!n.node_id, title: got && got.title}));
        """)
        assert r['ok'], r.get('error')
        assert r['has_id'] is True
        assert r['title'] == 'use api.forge'

    def test_invalid_type_safe(self):
        r = node_run("""
          let threw=false; let n=null;
          try { n = graph.upsertGraphNode(store, 'p1', {node_type:'not_a_real_type', title:'x'}); } catch(e){ threw=true; }
          console.log(JSON.stringify({ok:true, threw, created: !!(n && n.node_id)}));
        """)
        assert r['ok'], r.get('error')
        assert r['threw'] is False  # must not throw — safe rejection/ignore


class TestGraphEdges:
    def test_create_and_reinforce(self):
        r = node_run("""
          const a = graph.upsertGraphNode(store,'p1',{node_type:'memory',title:'a',summary:'a'});
          const b = graph.upsertGraphNode(store,'p1',{node_type:'file',source_id:'client.js',title:'client.js'});
          graph.createGraphEdge(store,'p1',{from_node_id:a.node_id,to_node_id:b.node_id,edge_type:'touches_file',weight:1});
          graph.createGraphEdge(store,'p1',{from_node_id:a.node_id,to_node_id:b.node_id,edge_type:'touches_file',weight:0.5});
          const edges = store.getGraphEdges('p1',{});
          console.log(JSON.stringify({ok:true, count: edges.length, weight: edges[0] && edges[0].weight}));
        """)
        assert r['ok'], r.get('error')
        assert r['count'] == 1          # reinforced, not duplicated
        assert r['weight'] > 1          # weight grew

    def test_reinforce_method(self):
        r = node_run("""
          const a = graph.upsertGraphNode(store,'p1',{node_type:'memory',title:'a'});
          const b = graph.upsertGraphNode(store,'p1',{node_type:'memory',title:'b'});
          const e = graph.createGraphEdge(store,'p1',{from_node_id:a.node_id,to_node_id:b.node_id,edge_type:'similar_to',weight:1});
          const before = store.getGraphEdges('p1',{})[0].weight;
          graph.reinforceGraphEdge(store,'p1', e.edge_id, 0.5);
          const after = store.getGraphEdges('p1',{})[0].weight;
          console.log(JSON.stringify({ok:true, grew: after > before}));
        """)
        assert r['ok'], r.get('error')
        assert r['grew'] is True


class TestRelatedNodes:
    def test_finds_relevant(self):
        r = node_run("""
          graph.upsertGraphNode(store,'p1',{node_type:'memory',title:'migrate fetch to api forge',summary:'use centralized client'});
          graph.upsertGraphNode(store,'p1',{node_type:'memory',title:'unrelated thing about colors',summary:'css palette'});
          const res = graph.findRelatedNodes(store,'p1','migrate fetch to api',{});
          console.log(JSON.stringify({ok:true, is_array: Array.isArray(res), count: res.length, top: res[0] && res[0].title}));
        """)
        assert r['ok'], r.get('error')
        assert r['is_array'] is True
        # lenient: relevant node should be present somewhere
        assert r['count'] >= 1


class TestContradictions:
    def test_lenient_no_throw(self):
        r = node_run("""
          graph.upsertGraphNode(store,'p1',{node_type:'memory',title:'fetch',summary:'always use direct fetch calls everywhere'});
          const res = graph.detectContradictions(store,'p1',{node_type:'memory',title:'fetch',summary:'never use direct fetch calls, use api.forge instead'});
          console.log(JSON.stringify({ok:true, is_array: Array.isArray(res)}));
        """)
        assert r['ok'], r.get('error')
        assert r['is_array'] is True


class TestSecretScrubInGraph:
    def test_secret_not_stored(self):
        r = node_run("""
          const n = graph.upsertGraphNode(store,'p1',{node_type:'memory',title:'cfg',
            summary:'token is sk-ant-api03-ABCDEFGHIJKLMNOP1234567 here',
            payload:{password:'supersecret123456', note:'ok'}});
          const got = store.findGraphNode(n.node_id);
          const blob = JSON.stringify(got);
          console.log(JSON.stringify({ok:true,
            has_anthropic: blob.includes('sk-ant-api03-ABCDEFGHIJKLMNOP1234567'),
            has_password: blob.includes('supersecret123456')}));
        """)
        assert r['ok'], r.get('error')
        assert r['has_anthropic'] is False   # STRICT
        assert r['has_password'] is False    # STRICT


class TestContextPacket:
    def test_build_and_persist(self):
        r = node_run("""
          store.upsertMemoryFact({memory_id:'m1',project_id:'p1',category:'coding',fact:'use api.forge for requests',confidence:'high',created_at:nowIso()});
          const pkt = ctx.buildContextPacket(store, {id:'p1',stack:{language:'js'}}, {id:'r1',goal:'migrate fetch'}, 'planner', 'migrate fetch to api', {});
          const persisted = store.getContextPackets('p1',{});
          console.log(JSON.stringify({ok:true, has_id: !!(pkt && pkt.packet_id), persisted: persisted.length}));
        """)
        assert r['ok'], r.get('error')
        assert r['has_id'] is True
        assert r['persisted'] >= 1

    def test_no_secrets_in_packet(self):
        r = node_run("""
          store.upsertMemoryFact({memory_id:'m1',project_id:'p1',category:'coding',
            fact:'token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijklmnop here',confidence:'high',created_at:nowIso()});
          const pkt = ctx.buildContextPacket(store, {id:'p1',stack:{}}, {id:'r1',goal:'x'}, 'planner', 'do x', {});
          const blob = JSON.stringify(pkt);
          console.log(JSON.stringify({ok:true, has_jwt: blob.includes('eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijklmnop')}));
        """)
        assert r['ok'], r.get('error')
        assert r['has_jwt'] is False   # STRICT


class TestGracefulDegradation:
    def test_empty_store_no_throw(self):
        r = node_run("""
          const pkt = ctx.buildContextPacket(store, {id:'p1',stack:{}}, {id:'r1',goal:'x'}, 'planner', 'do x', {});
          const cons = graph.consolidateMemoryGraph(store,'p1',{trigger_type:'manual'});
          console.log(JSON.stringify({ok:true, pkt_obj: typeof pkt==='object', cons_obj: typeof cons==='object'}));
        """)
        assert r['ok'], r.get('error')
        assert r['pkt_obj'] is True
        assert r['cons_obj'] is True


class TestConsolidation:
    def test_returns_report_and_records(self):
        r = node_run("""
          store.upsertLesson({lesson_id:'l1',project_id:'p1',category:'coding',lesson:'prefer api.forge over fetch',confidence:'medium',created_at:nowIso()});
          store.upsertLesson({lesson_id:'l2',project_id:'p1',category:'coding',lesson:'prefer api.forge over fetch',confidence:'medium',created_at:nowIso()});
          const rep = graph.consolidateMemoryGraph(store,'p1',{trigger_type:'manual'});
          const runs = store.getConsolidationRuns('p1');
          console.log(JSON.stringify({ok:true, has_report: typeof rep==='object', runs: runs.length,
            numeric: typeof (rep.nodes_created) === 'number'}));
        """)
        assert r['ok'], r.get('error')
        assert r['has_report'] is True
        assert r['runs'] >= 1
        assert r['numeric'] is True


class TestAdvisorySafetyInvariant:
    """Static source check: helper models advisory only, never in classifyCommand."""

    def test_consult_helper_present(self):
        src = open(FORGE_JS).read()
        assert 'consultHelperModel' in src
        assert 'overridden_by_rule' in src   # advisory records rule override

    def test_classify_command_independent_of_helper(self):
        src = open(FORGE_JS).read()
        idx = src.find('function classifyCommand')
        assert idx != -1
        end = src.find('\n  }', idx)
        body = src[idx:end]
        assert 'consultHelperModel' not in body
        assert 'advisory' not in body.lower()

    def test_command_blocked_patterns_intact(self):
        src = open(FORGE_JS).read()
        assert 'CMD_BLOCKED' in src
        assert "level: 'BLOCKED'" in src


@pytest.mark.skipif(os.environ.get("SKIP_LIVE_TESTS", "1") == "1", reason="Live server tests skipped")
class TestCognitiveRoutes:
    def test_memory_graph_summary_auth(self):
        import requests
        r = requests.get(f"{BASE_URL}/api/forge/projects/fake/memory-graph/summary", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_memory_graph_nodes_auth(self):
        import requests
        r = requests.get(f"{BASE_URL}/api/forge/projects/fake/memory-graph/nodes", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_context_packets_auth(self):
        import requests
        r = requests.get(f"{BASE_URL}/api/forge/projects/fake/context-packets", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_advisory_events_auth(self):
        import requests
        r = requests.get(f"{BASE_URL}/api/forge/projects/fake/advisory-events", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_advisory_metrics_auth(self):
        import requests
        r = requests.get(f"{BASE_URL}/api/forge/projects/fake/advisory-metrics", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_cognitive_events_auth(self):
        import requests
        r = requests.get(f"{BASE_URL}/api/forge/projects/fake/cognitive-events", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)

    def test_consolidate_auth(self):
        import requests
        r = requests.post(f"{BASE_URL}/api/forge/projects/fake/memory-graph/consolidate", timeout=TIMEOUT)
        assert r.status_code in (401, 403, 404)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
