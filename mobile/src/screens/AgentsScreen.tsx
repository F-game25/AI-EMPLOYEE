import React, { useState, useEffect } from 'react'
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  TextInput, RefreshControl, Alert,
} from 'react-native'
import * as Haptics from 'expo-haptics'
import { api } from '../api/secureClient'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

interface Agent {
  id: string; name: string; status: string; role: string
  last_active?: string; task_count?: number; success_rate?: number
}

const STATUS_COLOR: Record<string, string> = {
  running: Colors.green, active: Colors.green,
  idle: Colors.textDim, stopped: Colors.textDim,
  error: Colors.red, critical: Colors.red,
}

function AgentCard({ agent, onRun }: { agent: Agent; onRun: (a: Agent) => void }) {
  const color = STATUS_COLOR[agent.status] || Colors.textDim
  return (
    <TouchableOpacity style={styles.card} onPress={() => onRun(agent)} activeOpacity={0.8}>
      <View style={styles.cardTop}>
        <View style={[styles.dot, { backgroundColor: color }]} />
        <Text style={styles.name} numberOfLines={1}>{agent.name}</Text>
        <Text style={[styles.status, { color }]}>{agent.status.toUpperCase()}</Text>
      </View>
      <Text style={styles.role}>{agent.role}</Text>
      {agent.success_rate != null && (
        <View style={styles.cardBottom}>
          <Text style={styles.meta}>{Math.round(agent.success_rate * 100)}% success</Text>
          {agent.task_count != null && <Text style={styles.meta}>{agent.task_count} tasks</Text>}
        </View>
      )}
    </TouchableOpacity>
  )
}

export default function AgentsScreen() {
  const [agents, setAgents]     = useState<Agent[]>([])
  const [loading, setLoading]   = useState(false)
  const [filter, setFilter]     = useState('')
  const [taskInput, setTaskInput] = useState('')
  const [runTarget, setRunTarget] = useState<Agent | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.getAgents()
      setAgents(res.agents as Agent[] || [])
    } catch { setAgents([]) }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const handleRun = (agent: Agent) => {
    setRunTarget(agent)
    Alert.prompt(
      `Run ${agent.name}`,
      'Enter task description:',
      async (text) => {
        if (!text?.trim()) return
        await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)
        try {
          await api.triggerAgent(agent.id, text.trim())
          Alert.alert('Task queued', `${agent.name} is now running your task.`)
        } catch (e: unknown) {
          Alert.alert('Error', (e as { message?: string }).message || 'Failed to start task')
        }
      },
      'plain-text',
      '',
    )
  }

  const filtered = filter
    ? agents.filter(a => a.name.toLowerCase().includes(filter.toLowerCase()) || a.role?.toLowerCase().includes(filter.toLowerCase()))
    : agents

  return (
    <View style={styles.page}>
      <View style={styles.header}>
        <TextInput
          style={styles.search}
          placeholder="Search agents…"
          placeholderTextColor={Colors.textDim}
          value={filter}
          onChangeText={setFilter}
        />
      </View>

      <View style={styles.stats}>
        <Text style={styles.stat}>{agents.filter(a => a.status === 'running' || a.status === 'active').length} ACTIVE</Text>
        <Text style={styles.statDot}>·</Text>
        <Text style={styles.stat}>{agents.filter(a => a.status === 'error').length} ERRORS</Text>
        <Text style={styles.statDot}>·</Text>
        <Text style={styles.stat}>{agents.length} TOTAL</Text>
      </View>

      <FlatList
        data={filtered}
        keyExtractor={a => a.id}
        renderItem={({ item }) => <AgentCard agent={item} onRun={handleRun} />}
        contentContainerStyle={styles.list}
        numColumns={2}
        columnWrapperStyle={styles.row}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.gold} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>{loading ? 'Loading…' : filter ? 'No agents match' : 'No agents loaded'}</Text>
          </View>
        }
      />
    </View>
  )
}

const styles = StyleSheet.create({
  page:   { flex: 1, backgroundColor: Colors.bg },
  header: { padding: 12, paddingBottom: 0 },
  search: {
    backgroundColor: Colors.surface1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 6, padding: 10, color: Colors.text,
    fontFamily: Fonts.mono, fontSize: 12,
  },
  stats:    { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8 },
  stat:     { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1 },
  statDot:  { color: Colors.border },
  list:     { padding: 8, paddingBottom: 80 },
  row:      { gap: 8, marginBottom: 8 },

  card: {
    flex: 1, backgroundColor: Colors.surface1,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, padding: 12,
  },
  cardTop: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  dot:     { width: 6, height: 6, borderRadius: 3, marginRight: 6 },
  name:    { flex: 1, fontFamily: Fonts.mono, fontSize: 10, color: Colors.text },
  status:  { fontFamily: Fonts.mono, fontSize: 7, fontWeight: '700' },
  role:    { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim },
  cardBottom: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  meta:    { fontFamily: Fonts.mono, fontSize: 8, color: Colors.textDim },

  empty:     { flex: 1, alignItems: 'center', padding: 40 },
  emptyText: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.textDim },
})
