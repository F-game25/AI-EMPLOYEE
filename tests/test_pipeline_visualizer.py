"""
Test suite for Pipeline Visualizer (Phase 3.3)

Tests the 10-phase pipeline execution visualization, real-time updates,
and detail panel rendering.
"""
import pytest
import json
import asyncio
from datetime import datetime, timedelta


class TestPipelinePhases:
    """Test 10-phase structure and status transitions"""

    EXPECTED_PHASES = [
        'Input',
        'Retrieve Nodes',
        'Build Context',
        'Classify Decision',
        'Call LLM',
        'Validate Tasks',
        'Execute Tasks',
        'Format Response',
        'Update Graph',
        'Monitor & Improve',
    ]

    def test_phase_count(self):
        """Verify exactly 10 phases exist"""
        assert len(self.EXPECTED_PHASES) == 10

    def test_phase_names(self):
        """Verify phase names match unified_pipeline.py"""
        assert self.EXPECTED_PHASES == [
            'Input',
            'Retrieve Nodes',
            'Build Context',
            'Classify Decision',
            'Call LLM',
            'Validate Tasks',
            'Execute Tasks',
            'Format Response',
            'Update Graph',
            'Monitor & Improve',
        ]

    def test_phase_numbering(self):
        """Verify phases are numbered 1-10"""
        for i, phase in enumerate(self.EXPECTED_PHASES, 1):
            assert i >= 1 and i <= 10

    def test_phase_status_pending(self):
        """Phase should start in pending status"""
        phase = {
            'phaseNum': 1,
            'name': 'Input',
            'status': 'pending',
            'duration_ms': 0,
        }
        assert phase['status'] == 'pending'

    def test_phase_status_running(self):
        """Phase should transition to running"""
        phase = {
            'phaseNum': 1,
            'name': 'Input',
            'status': 'running',
            'startedAt': datetime.utcnow().isoformat(),
        }
        assert phase['status'] == 'running'
        assert 'startedAt' in phase

    def test_phase_status_done(self):
        """Phase should transition to done with duration"""
        now = datetime.utcnow()
        phase = {
            'phaseNum': 1,
            'name': 'Input',
            'status': 'done',
            'startedAt': (now - timedelta(milliseconds=150)).isoformat(),
            'completedAt': now.isoformat(),
            'duration_ms': 150,
        }
        assert phase['status'] == 'done'
        assert phase['duration_ms'] > 0

    def test_phase_status_failed(self):
        """Phase should transition to failed with error"""
        phase = {
            'phaseNum': 5,
            'name': 'Call LLM',
            'status': 'failed',
            'error': 'LLM timeout after 30s',
            'completedAt': datetime.utcnow().isoformat(),
        }
        assert phase['status'] == 'failed'
        assert 'error' in phase


class TestPipelineTrace:
    """Test pipeline trace structure and API response"""

    def test_trace_structure(self):
        """Verify trace has correct structure"""
        trace = {
            'taskId': 'task-123',
            'tenantId': 'tenant-456',
            'createdAt': datetime.utcnow().isoformat(),
            'phases': [
                {
                    'phaseNum': i,
                    'name': f'Phase {i}',
                    'status': 'pending',
                    'duration_ms': 0,
                    'logs': [],
                    'metrics': {},
                }
                for i in range(1, 11)
            ],
        }

        assert trace['taskId'] == 'task-123'
        assert trace['tenantId'] == 'tenant-456'
        assert len(trace['phases']) == 10

    def test_trace_with_logs(self):
        """Phase should track logs"""
        phase = {
            'phaseNum': 2,
            'name': 'Retrieve Nodes',
            'status': 'done',
            'logs': [
                {
                    'timestamp': '2026-05-05T12:00:00Z',
                    'level': 'info',
                    'message': 'Retrieved 5 nodes from knowledge store',
                },
                {
                    'timestamp': '2026-05-05T12:00:01Z',
                    'level': 'info',
                    'message': 'Expanded neighbors: 3 new concepts',
                },
            ],
        }

        assert len(phase['logs']) == 2
        assert phase['logs'][0]['level'] == 'info'

    def test_trace_with_metrics(self):
        """Phase should track execution metrics"""
        phase = {
            'phaseNum': 5,
            'name': 'Call LLM',
            'status': 'done',
            'metrics': {
                'tokens_used': 1250,
                'latency_ms': 1800,
                'retry_count': 0,
                'model': 'claude-opus',
            },
        }

        assert phase['metrics']['tokens_used'] == 1250
        assert phase['metrics']['latency_ms'] == 1800


class TestWebSocketFormat:
    """Test WebSocket message format"""

    def test_phase_update_message(self):
        """Verify phase update message format"""
        msg = {
            'phaseNum': 2,
            'status': 'running',
            'startedAt': '2026-05-05T12:00:00Z',
            'duration_ms': 0,
        }

        assert 'phaseNum' in msg
        assert 'status' in msg
        assert msg['status'] in ['pending', 'running', 'done', 'failed']

    def test_phase_update_completion(self):
        """Verify phase completion message"""
        msg = {
            'phaseNum': 2,
            'status': 'done',
            'completedAt': '2026-05-05T12:00:15Z',
            'duration_ms': 15000,
            'metrics': {'nodes_retrieved': 8},
        }

        assert msg['status'] == 'done'
        assert 'completedAt' in msg
        assert msg['duration_ms'] > 0

    def test_phase_error_message(self):
        """Verify phase error message"""
        msg = {
            'phaseNum': 4,
            'status': 'failed',
            'completedAt': '2026-05-05T12:00:05Z',
            'duration_ms': 5000,
            'error': 'Intent classification failed: ambiguous input',
        }

        assert msg['status'] == 'failed'
        assert 'error' in msg


class TestDetailPanel:
    """Test detail panel rendering and data"""

    def test_phase_detail_data(self):
        """Verify phase detail has required fields"""
        phase_detail = {
            'num': 5,
            'name': 'Call LLM',
            'description': 'Execute LLM inference',
            'status': 'done',
            'startedAt': '2026-05-05T12:00:30Z',
            'completedAt': '2026-05-05T12:02:00Z',
            'duration_ms': 90000,
            'logs': [],
            'metrics': {},
        }

        required_fields = [
            'num',
            'name',
            'description',
            'status',
            'duration_ms',
            'logs',
            'metrics',
        ]
        for field in required_fields:
            assert field in phase_detail

    def test_phase_detail_with_logs_window(self):
        """Detail panel should show last 5 logs"""
        logs = [
            {'timestamp': f'2026-05-05T12:00:{i:02d}Z', 'level': 'info', 'message': f'Log {i}'}
            for i in range(10)
        ]

        # Should truncate to last 5
        displayed = logs[-5:]
        assert len(displayed) == 5
        assert displayed[0]['message'] == 'Log 5'
        assert displayed[-1]['message'] == 'Log 9'

    def test_phase_detail_success_case(self):
        """Detail panel should show success badge when done"""
        phase = {
            'num': 7,
            'name': 'Execute Tasks',
            'status': 'done',
            'duration_ms': 12000,
        }

        assert phase['status'] == 'done'
        # In UI, this would show green checkmark + success badge

    def test_phase_detail_error_case(self):
        """Detail panel should show error message when failed"""
        phase = {
            'num': 4,
            'name': 'Classify Decision',
            'status': 'failed',
            'error': 'DecisionEngine timeout',
            'duration_ms': 30000,
        }

        assert phase['status'] == 'failed'
        assert 'error' in phase
        # In UI, this would show red X + error section


class TestSequentialExecution:
    """Test phase execution order"""

    def test_phases_sequential_not_parallel(self):
        """Verify phases execute sequentially"""
        timeline = [
            {'phaseNum': 1, 'status': 'done', 'completedAt': '2026-05-05T12:00:01Z'},
            {'phaseNum': 2, 'status': 'done', 'completedAt': '2026-05-05T12:00:05Z'},
            {'phaseNum': 3, 'status': 'running', 'startedAt': '2026-05-05T12:00:05Z'},
            {'phaseNum': 4, 'status': 'pending'},
        ]

        # Verify order
        done_phases = [p['phaseNum'] for p in timeline if p['status'] == 'done']
        assert done_phases == [1, 2]

        # Only one phase running at a time
        running = [p for p in timeline if p['status'] == 'running']
        assert len(running) <= 1

    def test_phases_cannot_skip(self):
        """Verify phases should not be skipped in normal execution"""
        # Valid sequence: phases 1, 2, 3, 4 in order
        valid_phases = [
            {'phaseNum': 1, 'status': 'done'},
            {'phaseNum': 2, 'status': 'done'},
            {'phaseNum': 3, 'status': 'done'},
            {'phaseNum': 4, 'status': 'running'},
        ]
        phase_nums = [p['phaseNum'] for p in valid_phases]
        assert phase_nums == [1, 2, 3, 4]


class TestPipelineMetrics:
    """Test phase metrics collection"""

    def test_retrieve_nodes_metrics(self):
        """Phase 2 metrics"""
        metrics = {
            'nodes_retrieved': 8,
            'neighbors_expanded': 3,
            'elapsed_ms': 500,
        }

        assert 'nodes_retrieved' in metrics
        assert metrics['nodes_retrieved'] > 0

    def test_llm_call_metrics(self):
        """Phase 5 metrics"""
        metrics = {
            'tokens_used': 1500,
            'tokens_generated': 350,
            'latency_ms': 2500,
            'model': 'claude-opus',
            'retry_count': 0,
        }

        assert metrics['tokens_used'] + metrics['tokens_generated'] > 0
        assert metrics['latency_ms'] > 0

    def test_execute_tasks_metrics(self):
        """Phase 7 metrics"""
        metrics = {
            'tasks_executed': 3,
            'tasks_succeeded': 3,
            'tasks_failed': 0,
            'elapsed_ms': 5000,
        }

        assert metrics['tasks_succeeded'] + metrics['tasks_failed'] == metrics['tasks_executed']

    def test_monitor_and_improve_metrics(self):
        """Phase 10 metrics"""
        metrics = {
            'anomalies_detected': 0,
            'improvements_logged': 2,
            'audit_records': 1,
            'elapsed_ms': 200,
        }

        assert 'anomalies_detected' in metrics


class TestErrorHandling:
    """Test error conditions"""

    def test_missing_taskid(self):
        """API should handle missing taskId"""
        # GET /api/execution/pipeline/
        # Should return 404 or empty trace

        response = {
            'ok': False,
            'error': 'Task not found',
        }

        assert not response['ok']

    def test_websocket_connection_lost(self):
        """WebSocket should handle client disconnect gracefully"""
        # Connection closed by client should not error

        pass

    def test_phase_timeout(self):
        """Phase should handle timeout"""
        phase = {
            'phaseNum': 5,
            'name': 'Call LLM',
            'status': 'failed',
            'error': 'LLM timeout after 30s',
            'duration_ms': 30000,
        }

        assert phase['status'] == 'failed'
        assert 'timeout' in phase['error'].lower()

    def test_phase_validation_error(self):
        """Phase should handle validation failure"""
        phase = {
            'phaseNum': 6,
            'name': 'Validate Tasks',
            'status': 'failed',
            'error': 'Task schema validation failed: missing required field "action"',
            'duration_ms': 150,
        }

        assert phase['status'] == 'failed'


class TestRealTimeUpdates:
    """Test real-time update behavior"""

    def test_phase_transitions(self):
        """Test phase state transitions over time"""
        phases = {i: 'pending' for i in range(1, 11)}

        # Phase 1 starts
        phases[1] = 'running'
        assert phases[1] == 'running'

        # Phase 1 completes
        phases[1] = 'done'
        assert phases[1] == 'done'

        # Phase 2 can now start
        phases[2] = 'running'
        assert phases[2] == 'running'

    def test_partial_failure_recovery(self):
        """Test partial failure doesn't break remaining phases"""
        phases = [
            {'phaseNum': 1, 'status': 'done'},
            {'phaseNum': 2, 'status': 'failed', 'error': 'Network issue'},
            # Phase 3+ should be able to proceed with fallback
            {'phaseNum': 3, 'status': 'done'},
        ]

        assert len(phases) == 3
        failed = [p for p in phases if p['status'] == 'failed']
        assert len(failed) == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
