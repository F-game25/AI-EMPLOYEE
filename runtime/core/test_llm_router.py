#!/usr/bin/env python3
"""Quick test of LLM provider router and phase reporting."""

import os
import sys
import asyncio
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_router():
    """Test that router initializes correctly."""
    from llm_provider_router import get_router, reset_router

    # Test 1: Router initializes (should work even without API keys)
    print("Test 1: Initializing router...")
    reset_router()
    router = get_router()
    print(f"  Primary provider: {router.primary_provider}")
    print(f"  Anthropic client: {router.anthropic_client}")
    print(f"  Ollama client: {router.ollama_client}")
    print(f"  OpenRouter client: {router.openrouter_client}")
    print("  ✓ Router initialized")

    # Test 2: Router selection logic
    print("\nTest 2: Testing provider selection...")
    client = router._get_client('anthropic')
    print(f"  _get_client('anthropic'): {client}")
    client = router._get_client('ollama')
    print(f"  _get_client('ollama'): {client}")
    client = router._get_client('openrouter')
    print(f"  _get_client('openrouter'): {client}")
    print("  ✓ Provider selection works")

    # Test 3: Simulate environment variable change
    print("\nTest 3: Testing provider switch via env var...")
    os.environ['LLM_PROVIDER'] = 'ollama'
    reset_router()
    router = get_router()
    print(f"  After env change, primary provider: {router.primary_provider}")
    assert router.primary_provider == 'ollama', "Provider should be ollama"
    print("  ✓ Provider switch works")

    print("\n✅ All router tests passed!")


# ── Phase Reporter Tests ──────────────────────────────────────────────────────


class MockPhaseUpdateHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler for /api/execution/phase-update endpoint."""

    received_updates = []

    def do_POST(self):
        """Handle POST requests to /api/execution/phase-update."""
        if self.path == "/api/execution/phase-update":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8"))
                MockPhaseUpdateHandler.received_updates.append(payload)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


async def test_phase_reporting():
    """Test that PhaseReporter sends correct payloads to backend."""
    from phase_reporter import PhaseReporter

    print("\nTest: Phase Reporting")

    # Start mock backend server
    MockPhaseUpdateHandler.received_updates = []
    server = HTTPServer(("127.0.0.1", 9999), MockPhaseUpdateHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # Create reporter and send phase updates
        reporter = PhaseReporter(
            backend_url="http://127.0.0.1:9999",
            task_id="test-task-123",
            tenant_id="test-tenant",
        )

        # Report phase 1
        success = reporter.report_phase(
            phase_num=1,
            phase_name="retrieve_relevant_nodes",
            status="running",
            input={"task": "test task"},
        )
        assert success, "Phase 1 report should succeed"

        # Report phase 1 done
        success = reporter.report_phase(
            phase_num=1,
            phase_name="retrieve_relevant_nodes",
            status="done",
            duration_ms=250,
            output={"nodes": ["node1", "node2"]},
        )
        assert success, "Phase 1 done report should succeed"

        # Report phase 4 (LLM call)
        success = reporter.report_phase(
            phase_num=4,
            phase_name="call_llm",
            status="running",
        )
        assert success, "Phase 4 report should succeed"

        # Verify received updates
        assert len(MockPhaseUpdateHandler.received_updates) == 3, \
            f"Should receive 3 updates, got {len(MockPhaseUpdateHandler.received_updates)}"

        # Check first update
        update1 = MockPhaseUpdateHandler.received_updates[0]
        assert update1["taskId"] == "test-task-123"
        assert update1["tenantId"] == "test-tenant"
        assert update1["phase"] == 1
        assert update1["phaseName"] == "retrieve_relevant_nodes"
        assert update1["status"] == "running"
        assert update1["input"]["task"] == "test task"

        # Check second update
        update2 = MockPhaseUpdateHandler.received_updates[1]
        assert update2["status"] == "done"
        assert update2["duration_ms"] == 250
        assert update2["output"]["nodes"] == ["node1", "node2"]

        print("  ✓ Phase reporter sends correct payloads")
        print("  ✓ Backend endpoint receives all phase updates")
        print("  ✓ Tenant context propagated correctly")

    finally:
        server.shutdown()

    print("\n✅ All phase reporting tests passed!")


if __name__ == '__main__':
    async def main():
        await test_router()
        await test_phase_reporting()

    asyncio.run(main())
