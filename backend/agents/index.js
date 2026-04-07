'use strict';

const agents = [
  { id: 'ai-1', name: 'LeadAnalyzer', status: 'working', task: 'Analyzing incoming lead data', type: 'analysis' },
  { id: 'ai-2', name: 'ResponseGen', status: 'idle', task: null, type: 'generation' },
  { id: 'ai-3', name: 'KnowledgeSearch', status: 'working', task: 'Searching knowledge base for CRM patterns', type: 'search' },
  { id: 'ai-4', name: 'TaskRouter', status: 'idle', task: null, type: 'routing' },
  { id: 'ai-5', name: 'DataExtractor', status: 'error', task: 'Failed to parse external API response', type: 'extraction' },
  { id: 'ai-6', name: 'ReportBuilder', status: 'idle', task: null, type: 'reporting' },
];

function getAgents() {
  return agents;
}

function updateAgentStatus(id, status, task) {
  const agent = agents.find((a) => a.id === id);
  if (!agent) return null;
  agent.status = status;
  agent.task = task !== undefined ? task : agent.task;
  return agent;
}

module.exports = { getAgents, updateAgentStatus };
