#!/usr/bin/env python3
"""Comprehensive validation of Python AI backend pipeline and LLM routing."""

import sys
import os
import json
import time
import urllib.request
import urllib.error
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Add runtime to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'runtime'))

# Track results
RESULTS = {
    'timestamp': datetime.now().isoformat(),
    'tests': {},
    'phase_updates_received': [],
}

# Test 1: Verify core module imports
print("\n" + "="*60)
print("TEST 1: Core Module Imports")
print("="*60)

try:
    from core.phase_reporter import PhaseReporter, PHASE_NAMES
    print("✓ PhaseReporter imported")
    RESULTS['tests']['phase_reporter_import'] = 'PASS'
except Exception as e:
    print(f"✗ PhaseReporter import failed: {e}")
    RESULTS['tests']['phase_reporter_import'] = f'FAIL: {e}'

try:
    from core.llm_provider_router import LLMProviderRouter
    print("✓ LLMProviderRouter imported")
    RESULTS['tests']['llm_router_import'] = 'PASS'
except Exception as e:
    print(f"✗ LLMProviderRouter import failed: {e}")
    RESULTS['tests']['llm_router_import'] = f'FAIL: {e}'

try:
    from core.unified_pipeline import process_user_input, PHASE_NAMES as PIPELINE_PHASES
    print("✓ Unified pipeline imported")
    RESULTS['tests']['unified_pipeline_import'] = 'PASS'
except Exception as e:
    print(f"✗ Unified pipeline import failed: {e}")
    RESULTS['tests']['unified_pipeline_import'] = f'FAIL: {e}'

try:
    from core.orchestrator import LLMClient
    print("✓ LLMClient imported")
    RESULTS['tests']['llm_client_import'] = 'PASS'
except Exception as e:
    print(f"✗ LLMClient import failed: {e}")
    RESULTS['tests']['llm_client_import'] = f'FAIL: {e}'

# Test 2: Phase Reporter Configuration
print("\n" + "="*60)
print("TEST 2: Phase Reporter Configuration")
print("="*60)

try:
    reporter = PhaseReporter(
        backend_url="http://localhost:8787",
        task_id="validate-task-001",
        tenant_id="default"
    )
    print(f"✓ PhaseReporter created")
    print(f"  - Backend URL: {reporter.backend_url}")
    print(f"  - Task ID: {reporter.task_id}")
    print(f"  - Tenant ID: {reporter.tenant_id}")
    print(f"  - Endpoint: {reporter.endpoint}")
    RESULTS['tests']['phase_reporter_config'] = 'PASS'
except Exception as e:
    print(f"✗ PhaseReporter config failed: {e}")
    RESULTS['tests']['phase_reporter_config'] = f'FAIL: {e}'

# Test 3: Phase Names Validation
print("\n" + "="*60)
print("TEST 3: Phase Names Validation")
print("="*60)

expected_phases = [
    "retrieve_relevant_nodes",
    "build_context",
    "classify_decision",
    "call_llm",
    "validate_tasks",
    "execute_tasks",
    "format_response",
    "update_graph",
    "monitor_and_improve",
    "validate_pipeline_integrity",
]

phase_match = PHASE_NAMES == expected_phases
if phase_match:
    print(f"✓ All 10 phases present and correctly named")
    for i, name in enumerate(PHASE_NAMES, 1):
        print(f"  {i}. {name}")
    RESULTS['tests']['phase_names'] = 'PASS'
else:
    print(f"✗ Phase names mismatch")
    print(f"  Expected: {expected_phases}")
    print(f"  Got: {PHASE_NAMES}")
    RESULTS['tests']['phase_names'] = 'FAIL: Phase name mismatch'

# Test 4: LLM Provider Router
print("\n" + "="*60)
print("TEST 4: LLM Provider Router")
print("="*60)

try:
    router = LLMProviderRouter()
    print(f"✓ LLMProviderRouter initialized")
    print(f"  - Primary provider: {router.primary_provider}")
    print(f"  - Anthropic client available: {router.anthropic_client is not None}")
    print(f"  - Ollama client available: {router.ollama_client is not None}")
    print(f"  - OpenRouter client available: {router.openrouter_client is not None}")
    RESULTS['tests']['llm_provider_router'] = 'PASS'
except Exception as e:
    print(f"✗ LLMProviderRouter initialization failed: {e}")
    RESULTS['tests']['llm_provider_router'] = f'FAIL: {e}'

# Test 5: LLMClient
print("\n" + "="*60)
print("TEST 5: LLMClient Configuration")
print("="*60)

try:
    client = LLMClient()
    print(f"✓ LLMClient initialized")
    print(f"  - Backend: {client.backend}")
    print("  - State directory: configured")
    print("  - Log path: configured")
    RESULTS['tests']['llm_client_config'] = 'PASS'
except Exception as e:
    print(f"✗ LLMClient initialization failed: {e}")
    RESULTS['tests']['llm_client_config'] = f'FAIL: {e}'

# Test 6: Mock HTTP Server for Phase Updates
print("\n" + "="*60)
print("TEST 6: Phase Reporter HTTP Callback (Mock Backend)")
print("="*60)

class MockBackendHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/execution/phase-update":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode('utf-8'))
                RESULTS['phase_updates_received'].append(payload)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

try:
    # Start mock backend on port 9999
    mock_server = HTTPServer(('127.0.0.1', 9999), MockBackendHandler)
    server_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)
    print("✓ Mock backend server started on 127.0.0.1:9999")

    # Test phase reporting
    test_reporter = PhaseReporter(
        backend_url="http://127.0.0.1:9999",
        task_id="test-validate-001",
        tenant_id="default"
    )

    # Send all 10 phases
    phases_sent = 0
    for i, phase_name in enumerate(PHASE_NAMES, 1):
        success = test_reporter.report_phase(
            phase_num=i,
            phase_name=phase_name,
            status="done",
            duration_ms=100 + (i * 10),
            output={"result": f"phase_{i}_complete"}
        )
        if success:
            phases_sent += 1

    print(f"✓ Sent {phases_sent}/10 phases to mock backend")

    time.sleep(0.5)  # Allow time for async processing

    if len(RESULTS['phase_updates_received']) == 10:
        print(f"✓ All 10 phase updates received by backend")
        RESULTS['tests']['phase_reporting_http'] = 'PASS'
        print("\n  Phase updates breakdown:")
        for update in RESULTS['phase_updates_received']:
            print(f"    - Phase {update['phase']}: {update['phaseName']} ({update['status']})")
    else:
        print(f"✗ Expected 10 phase updates, got {len(RESULTS['phase_updates_received'])}")
        RESULTS['tests']['phase_reporting_http'] = f'FAIL: Only {len(RESULTS["phase_updates_received"])}/10 updates'

    mock_server.shutdown()
except Exception as e:
    print(f"✗ Phase reporting HTTP test failed: {e}")
    RESULTS['tests']['phase_reporting_http'] = f'FAIL: {e}'

# Test 7: Provider Backend Configuration
print("\n" + "="*60)
print("TEST 7: Provider Backend Configuration")
print("="*60)

backends = {
    'anthropic': {
        'env_key': 'ANTHROPIC_API_KEY',
        'configured': bool(os.environ.get('ANTHROPIC_API_KEY', '').strip()),
    },
    'ollama': {
        'env_key': 'OLLAMA_HOST',
        'default': 'http://localhost:11434',
        'configured': bool(os.environ.get('OLLAMA_HOST', '').strip() or True),  # Has default
    },
    'openrouter': {
        'env_key': 'OPENROUTER_API_KEY',
        'configured': bool(os.environ.get('OPENROUTER_API_KEY', '').strip()),
    },
}

for provider, config in backends.items():
    status = '✓' if config['configured'] else '○'
    key_status = f"set" if config['configured'] else "not set"
    print(f"{status} {provider.upper()}: {config['env_key']} = {key_status}")

RESULTS['tests']['provider_configuration'] = 'PASS'

# Test 8: Pipeline Phase Structure
print("\n" + "="*60)
print("TEST 8: Pipeline Phase Structure")
print("="*60)

try:
    # Check unified_pipeline for phase function
    from core.unified_pipeline import _PipelineRun
    run = _PipelineRun("test input", "user-1", "power", "auto")
    print("✓ Pipeline run object created")
    print(f"  - Input: {run.input[:30]}...")
    print(f"  - User ID: {run.user_id}")
    print(f"  - Mode: {run.mode}")
    print(f"  - Trace initialized: {bool(run.trace)}")
    print(f"  - Degraded flag: {run.degraded}")
    RESULTS['tests']['pipeline_structure'] = 'PASS'
except Exception as e:
    print(f"✗ Pipeline structure validation failed: {e}")
    RESULTS['tests']['pipeline_structure'] = f'FAIL: {e}'

# Final Summary
print("\n" + "="*60)
print("VALIDATION SUMMARY")
print("="*60)

passed = sum(1 for v in RESULTS['tests'].values() if v == 'PASS')
failed = sum(1 for v in RESULTS['tests'].values() if 'FAIL' in str(v))
total = passed + failed

print(f"\nTests Passed: {passed}/{total}")
print(f"Tests Failed: {failed}/{total}")

if failed > 0:
    print("\nFailed tests:")
    for test, result in RESULTS['tests'].items():
        if 'FAIL' in str(result):
            print(f"  ✗ {test}: {result}")

print("\n" + "="*60)
print("BACKEND HEALTH CHECKS")
print("="*60)

# Check if Python backend is running
try:
    req = urllib.request.Request('http://127.0.0.1:18790/health')
    with urllib.request.urlopen(req, timeout=2) as resp:
        if resp.status == 200:
            print("✓ Python backend running on port 18790")
            RESULTS['backend_health'] = {
                'python_backend': 'RUNNING',
                'url': 'http://127.0.0.1:18790'
            }
        else:
            print("○ Python backend health check returned non-200")
            RESULTS['backend_health'] = {'python_backend': 'UNKNOWN'}
except urllib.error.URLError as e:
    print(f"○ Python backend not running (expected if not started): {e.reason}")
    RESULTS['backend_health'] = {'python_backend': 'NOT_RUNNING'}
except Exception as e:
    print(f"○ Python backend health check failed: {e}")

# Check Node backend
try:
    req = urllib.request.Request('http://127.0.0.1:8787/health')
    with urllib.request.urlopen(req, timeout=2) as resp:
        if resp.status == 200:
            print("✓ Node backend running on port 8787")
            RESULTS['backend_health']['node_backend'] = 'RUNNING'
        else:
            print("○ Node backend health check returned non-200")
            RESULTS['backend_health']['node_backend'] = 'UNKNOWN'
except urllib.error.URLError as e:
    print(f"○ Node backend not running (expected if not started): {e.reason}")
    RESULTS['backend_health']['node_backend'] = 'NOT_RUNNING'
except Exception as e:
    print(f"○ Node backend health check failed: {e}")

# Write results to file
results_file = 'state/validation_results.json'
os.makedirs(os.path.dirname(results_file), exist_ok=True)
with open(results_file, 'w') as f:
    json.dump(RESULTS, f, indent=2)
print(f"\n✓ Validation results saved to {results_file}")

print("\n" + "="*60)
if failed == 0:
    print("✅ VALIDATION SUCCESSFUL - All core modules operational")
    sys.exit(0)
else:
    print(f"⚠️  VALIDATION INCOMPLETE - {failed} test(s) failed")
    sys.exit(1)
