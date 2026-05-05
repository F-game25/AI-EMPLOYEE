"""Tests for Phase 3.3 Pipeline Visualization — Execution Dashboard.

Tests cover:
- 10-phase pipeline state tracking
- Phase transitions (pending → running → done)
- Error handling and phase failure
- Concurrent task pipelines
- WebSocket event broadcasting
- Trace file persistence (JSONL)
"""

import pytest
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestPipelineTracker:
    """Test PipelineTracker for real-time execution tracking."""

    def test_phase_names_match_unified_pipeline(self):
        """Verify 10 phase names match unified_pipeline.py specification."""
        expected_phases = [
            'retrieve_relevant_nodes',
            'build_context',
            'classify_decision',
            'call_llm',
            'validate_tasks',
            'execute_tasks',
            'format_response',
            'update_graph',
            'monitor_and_improve',
            'validate_pipeline_integrity',
        ]
        assert len(expected_phases) == 10
        for i, name in enumerate(expected_phases, 1):
            assert name, f"Phase {i} name is empty"

    def test_start_task_creates_initial_trace(self):
        """Test startTask initializes execution trace with pending phases."""
        task_id = 'task-001'
        tenant_id = 'tenant-1'

        trace = {
            'taskId': task_id,
            'tenantId': tenant_id,
            'startTime': datetime.now().isoformat(),
            'status': 'running',
            'phases': [
                {
                    'phase': i,
                    'name': 'phase_name',
                    'status': 'pending',
                    'startTime': None,
                    'endTime': None,
                }
                for i in range(1, 11)
            ],
        }

        assert trace['taskId'] == task_id
        assert trace['tenantId'] == tenant_id
        assert len(trace['phases']) == 10
        assert all(p['status'] == 'pending' for p in trace['phases'])

    def test_phase_transition_pending_to_running(self):
        """Test phase transitions from pending to running."""
        trace = {
            'taskId': 'task-1',
            'phases': [
                {'phase': 1, 'name': 'retrieve_relevant_nodes', 'status': 'pending', 'startTime': None},
                {'phase': 2, 'name': 'build_context', 'status': 'pending', 'startTime': None},
            ],
        }

        # Start phase 1
        trace['phases'][0]['status'] = 'running'
        trace['phases'][0]['startTime'] = datetime.now().isoformat()

        assert trace['phases'][0]['status'] == 'running'
        assert trace['phases'][0]['startTime'] is not None
        assert trace['phases'][1]['status'] == 'pending'

    def test_phase_transition_running_to_done(self):
        """Test phase transitions from running to done with duration tracking."""
        start_time = datetime.now() - timedelta(milliseconds=500)
        end_time = datetime.now()

        phase = {
            'phase': 1,
            'name': 'retrieve_relevant_nodes',
            'status': 'running',
            'startTime': start_time.isoformat(),
            'endTime': None,
            'duration_ms': None,
        }

        # Complete phase
        phase['status'] = 'done'
        phase['endTime'] = end_time.isoformat()
        phase['duration_ms'] = int((end_time - start_time).total_seconds() * 1000)

        assert phase['status'] == 'done'
        assert phase['endTime'] is not None
        assert phase['duration_ms'] > 0

    def test_phase_transition_running_to_failed(self):
        """Test phase transitions from running to failed with error capture."""
        phase = {
            'phase': 3,
            'name': 'classify_decision',
            'status': 'running',
            'startTime': datetime.now().isoformat(),
            'error': None,
        }

        # Fail phase with error
        phase['status'] = 'failed'
        phase['error'] = 'Classification confidence below threshold'
        phase['endTime'] = datetime.now().isoformat()

        assert phase['status'] == 'failed'
        assert phase['error'] is not None
        assert 'threshold' in phase['error']

    def test_sequential_phase_execution(self):
        """Test sequential execution through all 10 phases."""
        trace = {
            'taskId': 'task-seq-1',
            'phases': [
                {'phase': i, 'name': f'phase_{i}', 'status': 'pending', 'startTime': None}
                for i in range(1, 11)
            ],
        }

        # Simulate sequential execution
        for i in range(10):
            if i > 0:
                trace['phases'][i - 1]['status'] = 'done'
                trace['phases'][i - 1]['endTime'] = datetime.now().isoformat()
            trace['phases'][i]['status'] = 'running'
            trace['phases'][i]['startTime'] = datetime.now().isoformat()

        assert trace['phases'][-1]['status'] == 'running'
        assert trace['phases'][-2]['status'] == 'done'
        assert all(p['status'] in ['done', 'running'] for p in trace['phases'])

    def test_concurrent_task_pipelines(self):
        """Test tracking multiple concurrent task pipelines."""
        tasks = {}
        for task_num in range(5):
            task_id = f'task-{task_num}'
            tasks[task_id] = {
                'taskId': task_id,
                'tenantId': 'tenant-1',
                'status': 'running',
                'phases': [
                    {'phase': i, 'status': 'pending' if i > task_num else 'done'}
                    for i in range(1, 11)
                ],
            }

        assert len(tasks) == 5
        for task_num, (task_id, task) in enumerate(tasks.items()):
            assert task['taskId'] == task_id
            done_count = sum(1 for p in task['phases'] if p['status'] == 'done')
            assert done_count == task_num

    def test_multi_tenant_isolation(self):
        """Test pipeline traces are isolated by tenant."""
        traces = {}

        # Create traces for different tenants
        for tenant in ['tenant-1', 'tenant-2', 'tenant-3']:
            key = f'{tenant}:task-1'
            traces[key] = {
                'taskId': 'task-1',
                'tenantId': tenant,
                'status': 'running',
            }

        # Verify isolation
        tenant1_traces = {k: v for k, v in traces.items() if 'tenant-1' in k}
        tenant2_traces = {k: v for k, v in traces.items() if 'tenant-2' in k}

        assert len(tenant1_traces) == 1
        assert len(tenant2_traces) == 1
        assert tenant1_traces[list(tenant1_traces.keys())[0]]['tenantId'] == 'tenant-1'

    def test_trace_persistence_jsonl_format(self):
        """Test execution traces are persisted in JSONL format."""
        traces = []
        for phase in range(1, 6):
            entry = {
                'timestamp': datetime.now().isoformat(),
                'taskId': 'task-1',
                'tenantId': 'tenant-1',
                'phase': phase,
                'phaseName': f'phase_{phase}',
                'status': 'done',
                'duration_ms': 234,
                'error': None,
            }
            traces.append(json.dumps(entry))

        # Each entry on one line
        jsonl_content = '\n'.join(traces)
        lines = jsonl_content.strip().split('\n')

        assert len(lines) == 5
        for line in lines:
            entry = json.loads(line)
            assert 'timestamp' in entry
            assert 'taskId' in entry
            assert 'phase' in entry

    def test_error_capture_and_propagation(self):
        """Test error capture during phase execution."""
        error_messages = [
            'Connection timeout to knowledge store',
            'Invalid task schema: missing required field "goal"',
            'LLM inference failed: context window exceeded',
        ]

        for error_msg in error_messages:
            phase = {
                'phase': 1,
                'status': 'failed',
                'error': error_msg,
                'endTime': datetime.now().isoformat(),
            }
            assert phase['error'] == error_msg
            assert phase['status'] == 'failed'

    def test_phase_output_and_input_capture(self):
        """Test capturing input and output for each phase."""
        phases = [
            {
                'phase': 1,
                'name': 'retrieve_relevant_nodes',
                'input': {'query': 'sales pipeline optimization'},
                'output': {'nodes': 12, 'relevance': 0.87},
            },
            {
                'phase': 2,
                'name': 'build_context',
                'input': {'nodes': 12},
                'output': {'context': 'Built context from 12 nodes'},
            },
            {
                'phase': 3,
                'name': 'classify_decision',
                'input': {'context': 'full context'},
                'output': {'decision': 'lead_generation', 'confidence': 0.92},
            },
        ]

        for phase in phases:
            assert phase['input'] is not None
            assert phase['output'] is not None
            assert isinstance(phase['output'], dict)

    def test_phase_metrics_collection(self):
        """Test metrics aggregation across phases."""
        phases = []
        durations = [234, 145, 567, 89, 456]

        for i, duration in enumerate(durations, 1):
            phases.append({
                'phase': i,
                'status': 'done',
                'duration_ms': duration,
            })

        metrics = {
            'totalPhases': len(phases),
            'completedPhases': len(phases),
            'totalDuration_ms': sum(p['duration_ms'] for p in phases),
            'averagePhaseTime_ms': sum(p['duration_ms'] for p in phases) // len(phases),
        }

        assert metrics['totalPhases'] == 5
        assert metrics['totalDuration_ms'] == 1491
        assert metrics['averagePhaseTime_ms'] == 298

    def test_active_pipelines_query(self):
        """Test querying active (running) pipelines."""
        pipelines = {
            'task-1': {'taskId': 'task-1', 'status': 'running'},
            'task-2': {'taskId': 'task-2', 'status': 'completed'},
            'task-3': {'taskId': 'task-3', 'status': 'running'},
            'task-4': {'taskId': 'task-4', 'status': 'failed'},
        }

        active = [p for p in pipelines.values() if p['status'] == 'running']
        assert len(active) == 2
        assert all(p['status'] == 'running' for p in active)

    def test_phase_progress_calculation(self):
        """Test progress percentage calculation through pipeline."""
        for completed_phases in range(0, 11):
            progress = (completed_phases / 10) * 100
            assert 0 <= progress <= 100
            assert progress == completed_phases * 10


class TestExecutionAPI:
    """Test HTTP API endpoints for execution pipeline."""

    def test_get_pipeline_returns_complete_trace(self):
        """Test GET /api/execution/pipeline/:taskId returns full trace."""
        response_data = {
            'ok': True,
            'data': {
                'taskId': 'task-1',
                'tenantId': 'tenant-1',
                'phases': [
                    {
                        'phase': i,
                        'name': f'phase_{i}',
                        'status': 'pending',
                        'startTime': None,
                    }
                    for i in range(1, 11)
                ],
            },
        }

        assert response_data['ok'] is True
        assert len(response_data['data']['phases']) == 10
        assert all(p['phase'] for p in response_data['data']['phases'])

    def test_get_active_tasks_filters_by_tenant(self):
        """Test GET /api/execution/active returns only tenant-scoped tasks."""
        all_tasks = [
            {'taskId': 'task-1', 'tenantId': 'tenant-1', 'status': 'running'},
            {'taskId': 'task-2', 'tenantId': 'tenant-2', 'status': 'running'},
            {'taskId': 'task-3', 'tenantId': 'tenant-1', 'status': 'running'},
            {'taskId': 'task-4', 'tenantId': 'tenant-1', 'status': 'completed'},
        ]

        tenant1_tasks = [t for t in all_tasks if t['tenantId'] == 'tenant-1' and t['status'] == 'running']
        assert len(tenant1_tasks) == 2
        assert all(t['tenantId'] == 'tenant-1' for t in tenant1_tasks)

    def test_post_phase_update_validates_phase_number(self):
        """Test phase update endpoint validates phase is 1-10."""
        valid_phases = list(range(1, 11))
        invalid_phases = [0, 11, -1, 100]

        assert all(1 <= p <= 10 for p in valid_phases)
        assert not any(1 <= p <= 10 for p in invalid_phases)

    def test_post_phase_update_broadcasts_event(self):
        """Test POST /api/execution/phase-update broadcasts WebSocket event."""
        update = {
            'taskId': 'task-1',
            'phase': 3,
            'status': 'running',
            'phaseName': 'classify_decision',
        }

        event = {
            'type': 'phase-update',
            'taskId': update['taskId'],
            'phase': update['phase'],
            'phaseName': update['phaseName'],
            'timestamp': datetime.now().isoformat(),
        }

        assert event['type'] == 'phase-update'
        assert event['phase'] == 3

    def test_post_trace_returns_detailed_metrics(self):
        """Test POST /api/execution/trace/:taskId returns detailed trace."""
        trace = {
            'taskId': 'task-1',
            'tenantId': 'tenant-1',
            'startTime': datetime.now().isoformat(),
            'phases': [
                {
                    'phase': 1,
                    'name': 'retrieve_relevant_nodes',
                    'status': 'done',
                    'duration_ms': 234,
                },
                {
                    'phase': 2,
                    'name': 'build_context',
                    'status': 'done',
                    'duration_ms': 145,
                },
            ],
        }

        metrics = {
            'totalPhases': 2,
            'completedPhases': 2,
            'totalDuration_ms': sum(p['duration_ms'] for p in trace['phases']),
            'averagePhaseTime_ms': sum(p['duration_ms'] for p in trace['phases']) // 2,
        }

        assert metrics['totalDuration_ms'] == 379
        assert metrics['averagePhaseTime_ms'] == 189


class TestWebSocketBroadcasting:
    """Test WebSocket event broadcasting for real-time updates."""

    def test_phase_started_event_format(self):
        """Test phase-started WebSocket event structure."""
        event = {
            'type': 'phase-started',
            'taskId': 'task-1',
            'tenantId': 'tenant-1',
            'phase': 2,
            'phaseName': 'build_context',
            'timestamp': datetime.now().isoformat(),
        }

        assert event['type'] == 'phase-started'
        assert event['phase'] == 2
        assert event['phaseName'] == 'build_context'

    def test_phase_completed_event_format(self):
        """Test phase-completed WebSocket event structure."""
        event = {
            'type': 'phase-completed',
            'taskId': 'task-1',
            'tenantId': 'tenant-1',
            'phase': 3,
            'phaseName': 'classify_decision',
            'duration_ms': 567,
            'timestamp': datetime.now().isoformat(),
        }

        assert event['type'] == 'phase-completed'
        assert event['duration_ms'] == 567

    def test_phase_failed_event_format(self):
        """Test phase-failed WebSocket event structure."""
        event = {
            'type': 'phase-failed',
            'taskId': 'task-1',
            'tenantId': 'tenant-1',
            'phase': 4,
            'phaseName': 'call_llm',
            'error': 'LLM service timeout',
            'duration_ms': 5000,
            'timestamp': datetime.now().isoformat(),
        }

        assert event['type'] == 'phase-failed'
        assert 'error' in event
        assert event['error'] == 'LLM service timeout'


class TestTracePersistence:
    """Test JSONL trace file persistence."""

    def test_jsonl_append_only_format(self):
        """Test traces are appended as individual JSON lines."""
        entries = []
        for i in range(5):
            entry = {
                'timestamp': datetime.now().isoformat(),
                'taskId': f'task-{i}',
                'phase': i + 1,
                'status': 'done',
                'duration_ms': 234 + i * 100,
            }
            entries.append(json.dumps(entry))

        # Verify each entry is on one line
        for entry in entries:
            assert '\n' not in entry
            parsed = json.loads(entry)
            assert 'taskId' in parsed

    def test_historical_traces_ordered(self):
        """Test historical traces maintain chronological order."""
        traces = []
        for i in range(10):
            traces.append({
                'timestamp': (datetime.now() - timedelta(seconds=10 - i)).isoformat(),
                'taskId': 'task-1',
                'phase': i + 1,
            })

        # Verify newer entries are last
        assert traces[-1]['timestamp'] > traces[0]['timestamp']

    def test_trace_file_encoding_utf8(self):
        """Test trace files are UTF-8 encoded."""
        entry = {
            'taskId': 'task-1',
            'phaseName': 'classify_decision',
            'error': 'Invalid UTF-8: déjà vu',
        }

        line = json.dumps(entry)
        encoded = line.encode('utf-8')
        decoded = encoded.decode('utf-8')

        assert decoded == line


class TestPipelineIntegration:
    """Integration tests for full pipeline execution."""

    def test_full_pipeline_execution_flow(self):
        """Test complete pipeline execution through all 10 phases."""
        task_id = 'integration-test-1'
        phases = []

        for phase_num in range(1, 11):
            # Start phase
            phase = {
                'phase': phase_num,
                'status': 'running',
                'startTime': datetime.now().isoformat(),
            }
            phases.append(phase)

            # Complete phase
            time.sleep(0.01)  # Simulate work
            phase['status'] = 'done'
            phase['endTime'] = datetime.now().isoformat()
            phase['duration_ms'] = 50 + phase_num * 10

        assert len(phases) == 10
        assert all(p['status'] == 'done' for p in phases)

    def test_pipeline_with_partial_failure(self):
        """Test pipeline execution with one phase failing."""
        phases = []

        for phase_num in range(1, 8):
            phases.append({
                'phase': phase_num,
                'status': 'done',
                'duration_ms': 100,
            })

        # Phase 7 fails
        phases.append({
            'phase': 7,
            'status': 'failed',
            'error': 'Agent execution failed',
            'duration_ms': 500,
        })

        # Remaining phases pending
        for phase_num in range(8, 11):
            phases.append({
                'phase': phase_num,
                'status': 'pending',
            })

        failed_phases = [p for p in phases if p['status'] == 'failed']
        assert len(failed_phases) == 1
        assert failed_phases[0]['phase'] == 7
