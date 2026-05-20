import React, { useEffect, useCallback } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  RefreshControl, ActivityIndicator,
} from 'react-native'
import { useDashboardStore } from '../store/dashboardStore'
import { useAuthStore } from '../store/authStore'
import { ws } from '../api/secureClient'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

// ── KPI Tile ────────────────────────────────────────────────────────────────
function KPITile({ label, value, unit = '', color = Colors.gold, sub }: {
  label: string; value: string | number; unit?: string; color?: string; sub?: string
}) {
  return (
    <View style={[styles.kpiTile, { borderColor: `${color}30` }]}>
      <Text style={[styles.kpiValue, { color }]}>{value}<Text style={styles.kpiUnit}>{unit}</Text></Text>
      <Text style={styles.kpiLabel}>{label}</Text>
      {sub && <Text style={styles.kpiSub}>{sub}</Text>}
    </View>
  )
}

// ── Agent Row ───────────────────────────────────────────────────────────────
function AgentRow({ agent }: { agent: { id: string; name: string; status: string; role?: string } }) {
  const statusColor = agent.status === 'running' || agent.status === 'active'
    ? Colors.green
    : agent.status === 'error'
    ? Colors.red
    : Colors.textDim

  return (
    <View style={styles.agentRow}>
      <View style={[styles.agentDot, { backgroundColor: statusColor }]} />
      <Text style={styles.agentName} numberOfLines={1}>{agent.name}</Text>
      <Text style={[styles.agentStatus, { color: statusColor }]}>{agent.status.toUpperCase()}</Text>
    </View>
  )
}

// ── Task Card ───────────────────────────────────────────────────────────────
function TaskCard({ task }: { task: { id: string; title: string; status: string; agent: string; progress: number } }) {
  const progress = Math.min(100, Math.max(0, task.progress || 0))
  return (
    <View style={styles.taskCard}>
      <View style={styles.taskHeader}>
        <Text style={styles.taskTitle} numberOfLines={1}>{task.title}</Text>
        <Text style={styles.taskAgent}>{task.agent}</Text>
      </View>
      <View style={styles.progressTrack}>
        <View style={[styles.progressBar, { width: `${progress}%` as `${number}%` }]} />
      </View>
      <Text style={styles.taskPct}>{progress}%</Text>
    </View>
  )
}

// ── Section ─────────────────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  )
}

// ── Main Screen ──────────────────────────────────────────────────────────────
export default function DashboardScreen() {
  const { refresh, loading, systemHealth, agents, activeTasks, revenueStats, threatScore, lastTick, updateFromWs } = useDashboardStore()
  const { user, logout, wsConnected } = useAuthStore()

  useEffect(() => {
    refresh()

    const unsubConn = ws.on('connection', (_, data) => {
      useAuthStore.getState().setWsState((data as { status: string }).status === 'connected')
    })
    const unsubAll = ws.on('*', (_, msg) => {
      const m = msg as { type: string; data: unknown }
      updateFromWs(m.type, m.data)
    })

    return () => { unsubConn(); unsubAll() }
  }, [])

  const onRefresh = useCallback(() => refresh(), [refresh])

  const cpu = systemHealth?.cpu_percent ?? 0
  const ram = systemHealth?.memory_percent ?? 0
  const activeAgents = agents.filter(a => a.status === 'running' || a.status === 'active').length
  const runningTasks  = activeTasks.filter(t => t.status === 'executing' || t.status === 'running').length

  return (
    <View style={styles.page}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <View>
          <Text style={styles.topTitle}>NEXUS OS</Text>
          <Text style={styles.topSub}>{user?.email || 'Dashboard'}</Text>
        </View>
        <View style={styles.topRight}>
          <View style={[styles.wsBadge, { backgroundColor: wsConnected ? `${Colors.green}20` : `${Colors.red}20` }]}>
            <View style={[styles.wsDot, { backgroundColor: wsConnected ? Colors.green : Colors.red }]} />
            <Text style={[styles.wsLabel, { color: wsConnected ? Colors.green : Colors.red }]}>
              {wsConnected ? 'LIVE' : 'OFF'}
            </Text>
          </View>
          <TouchableOpacity onPress={logout} style={styles.logoutBtn}>
            <Text style={styles.logoutText}>⎋</Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading && !systemHealth ? (
        <View style={styles.loadingCenter}>
          <ActivityIndicator color={Colors.gold} size="large" />
          <Text style={styles.loadingText}>Connecting to system…</Text>
        </View>
      ) : (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={onRefresh} tintColor={Colors.gold} />}
        >
          {/* KPI strip */}
          <View style={styles.kpiRow}>
            <KPITile label="AGENTS"  value={activeAgents} color={Colors.green}  sub={`${agents.length} total`} />
            <KPITile label="TASKS"   value={runningTasks}  color={Colors.cyan}   sub={`${activeTasks.length} queued`} />
            <KPITile label="CPU"     value={Math.round(cpu)}  unit="%" color={cpu > 80 ? Colors.red : cpu > 60 ? Colors.orange : Colors.gold} />
            <KPITile label="RAM"     value={Math.round(ram)}  unit="%" color={ram > 80 ? Colors.red : ram > 60 ? Colors.orange : Colors.gold} />
          </View>

          {/* Revenue + Threat */}
          <View style={styles.kpiRow}>
            <KPITile
              label="MTD REVENUE"
              value={revenueStats ? `$${(revenueStats.mtd / 1000).toFixed(1)}k` : '—'}
              color={Colors.gold}
              sub={revenueStats ? `$${revenueStats.daily}/day` : ''}
            />
            <KPITile
              label="THREAT SCORE"
              value={threatScore}
              color={threatScore > 70 ? Colors.red : threatScore > 40 ? Colors.orange : Colors.green}
              sub={threatScore > 70 ? 'CRITICAL' : threatScore > 40 ? 'ELEVATED' : 'CLEAR'}
            />
          </View>

          {/* Active tasks */}
          {activeTasks.length > 0 && (
            <Section title="ACTIVE TASKS">
              {activeTasks.slice(0, 5).map(t => <TaskCard key={t.id} task={t} />)}
            </Section>
          )}

          {/* Agent fleet */}
          <Section title={`AGENT FLEET (${agents.length})`}>
            {agents.length === 0
              ? <Text style={styles.emptyText}>No agents loaded</Text>
              : agents.slice(0, 12).map(a => <AgentRow key={a.id} agent={a} />)
            }
          </Section>

          {/* Last update */}
          {lastTick > 0 && (
            <Text style={styles.timestamp}>
              Updated {new Date(lastTick).toLocaleTimeString()}
            </Text>
          )}
        </ScrollView>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: Colors.bg },

  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: 12, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgDeep,
  },
  topTitle: { fontFamily: Fonts.mono, fontSize: 12, color: Colors.gold, letterSpacing: 3 },
  topSub:   { fontFamily: Fonts.mono, fontSize: 9,  color: Colors.textDim, marginTop: 2 },
  topRight: { flexDirection: 'row', alignItems: 'center', gap: 10 },

  wsBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    borderRadius: 4, paddingHorizontal: 8, paddingVertical: 4,
  },
  wsDot:   { width: 5, height: 5, borderRadius: 3 },
  wsLabel: { fontFamily: Fonts.mono, fontSize: 8, fontWeight: '700' },

  logoutBtn:  { padding: 8 },
  logoutText: { fontSize: 18, color: Colors.textDim },

  loadingCenter: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingText:   { fontFamily: Fonts.mono, fontSize: 11, color: Colors.textDim },

  scroll:        { flex: 1 },
  scrollContent: { padding: 12, gap: 12 },

  kpiRow: { flexDirection: 'row', gap: 8 },
  kpiTile: {
    flex: 1, backgroundColor: Colors.surface1,
    borderWidth: 1, borderRadius: 8,
    padding: 10, alignItems: 'center',
  },
  kpiValue: { fontFamily: Fonts.mono, fontSize: 22, fontWeight: '700', lineHeight: 26 },
  kpiUnit:  { fontSize: 12, fontWeight: '400' },
  kpiLabel: { fontFamily: Fonts.mono, fontSize: 7, color: Colors.textDim, letterSpacing: 1, marginTop: 3 },
  kpiSub:   { fontFamily: Fonts.mono, fontSize: 7, color: Colors.textDim, marginTop: 2 },

  section:      { backgroundColor: Colors.surface1, borderWidth: 1, borderColor: Colors.border, borderRadius: 8, padding: 12 },
  sectionTitle: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1.5, marginBottom: 10 },
  emptyText:    { fontFamily: Fonts.mono, fontSize: 10, color: Colors.textDim, textAlign: 'center', paddingVertical: 8 },

  agentRow:   { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: Colors.borderFaint },
  agentDot:   { width: 6, height: 6, borderRadius: 3, marginRight: 10 },
  agentName:  { flex: 1, fontFamily: Fonts.mono, fontSize: 11, color: Colors.textMuted },
  agentStatus:{ fontFamily: Fonts.mono, fontSize: 8, fontWeight: '700' },

  taskCard: { backgroundColor: Colors.surface2, borderRadius: 6, padding: 10, marginBottom: 8 },
  taskHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  taskTitle:  { flex: 1, fontFamily: Fonts.mono, fontSize: 11, color: Colors.text },
  taskAgent:  { fontFamily: Fonts.mono, fontSize: 9, color: Colors.gold },
  progressTrack: { height: 2, backgroundColor: Colors.border, borderRadius: 1, marginBottom: 4 },
  progressBar:   { height: 2, backgroundColor: Colors.gold, borderRadius: 1 },
  taskPct:    { fontFamily: Fonts.mono, fontSize: 8, color: Colors.textDim, textAlign: 'right' },

  timestamp: { fontFamily: Fonts.mono, fontSize: 8, color: Colors.textDim, textAlign: 'center', paddingVertical: 8 },
})
