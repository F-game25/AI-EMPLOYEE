import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  RefreshControl, Modal, ScrollView, TextInput,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native'
import * as Haptics from 'expo-haptics'
import { useTasksStore, Task } from '../store/tasksStore'
import { useWebSocketEvents } from '../hooks/useWebSocketEvents'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

// ── Status color map ─────────────────────────────────────────────────────────

const statusColor = (status: string): string => {
  switch (status) {
    case 'running':
    case 'executing': return Colors.cyan
    case 'completed':
    case 'success':   return Colors.green
    case 'failed':
    case 'error':     return Colors.red
    case 'pending':   return Colors.gold
    default:          return Colors.textDim
  }
}

// ── Progress bar ─────────────────────────────────────────────────────────────

function ProgressBar({ pct, color }: { pct: number; color: string }) {
  const clamped = Math.min(100, Math.max(0, pct || 0))
  return (
    <View style={styles.track}>
      <View style={[styles.bar, { width: `${clamped}%` as `${number}%`, backgroundColor: color }]} />
    </View>
  )
}

// ── Task row ─────────────────────────────────────────────────────────────────

function TaskRow({ task, onPress }: { task: Task; onPress: () => void }) {
  const col = statusColor(task.status)
  const pct = Math.min(100, Math.max(0, task.progress || 0))
  return (
    <TouchableOpacity style={styles.taskRow} onPress={onPress} activeOpacity={0.8}>
      <View style={styles.taskHeader}>
        <View style={[styles.statusDot, { backgroundColor: col }]} />
        <Text style={styles.taskTitle} numberOfLines={1}>{task.title}</Text>
        <Text style={[styles.statusBadge, { color: col }]}>{task.status.toUpperCase()}</Text>
      </View>
      <Text style={styles.agentLabel}>{task.agent || 'orchestrator'}</Text>
      <ProgressBar pct={pct} color={col} />
      <Text style={styles.pctLabel}>{pct}%</Text>
    </TouchableOpacity>
  )
}

// ── Detail modal ─────────────────────────────────────────────────────────────

function TaskDetailModal({ task, onClose }: { task: Task | null; onClose: () => void }) {
  if (!task) return null
  const col = statusColor(task.status)
  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.sheet}>
          <View style={styles.sheetHandle} />
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle} numberOfLines={2}>{task.title}</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Text style={styles.closeBtnText}>✕</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.sheetScroll} contentContainerStyle={styles.sheetContent}>
            {/* Status row */}
            <View style={styles.detailRow}>
              <Text style={styles.detailKey}>STATUS</Text>
              <Text style={[styles.detailVal, { color: col }]}>{task.status.toUpperCase()}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailKey}>AGENT</Text>
              <Text style={[styles.detailVal, { color: Colors.gold }]}>{task.agent || '—'}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailKey}>PROGRESS</Text>
              <Text style={styles.detailVal}>{task.progress || 0}%</Text>
            </View>
            {task.elapsed_ms != null && (
              <View style={styles.detailRow}>
                <Text style={styles.detailKey}>ELAPSED</Text>
                <Text style={styles.detailVal}>{(task.elapsed_ms / 1000).toFixed(1)}s</Text>
              </View>
            )}

            <ProgressBar pct={task.progress || 0} color={col} />

            {/* Result */}
            {task.result ? (
              <View style={styles.resultBox}>
                <Text style={styles.resultLabel}>RESULT</Text>
                <Text style={styles.resultText}>{task.result}</Text>
              </View>
            ) : task.error ? (
              <View style={[styles.resultBox, styles.resultBoxError]}>
                <Text style={[styles.resultLabel, { color: Colors.red }]}>ERROR</Text>
                <Text style={[styles.resultText, { color: Colors.red }]}>{task.error}</Text>
              </View>
            ) : null}
          </ScrollView>
        </View>
      </View>
    </Modal>
  )
}

// ── Run task sheet ────────────────────────────────────────────────────────────

function RunTaskSheet({ onClose }: { onClose: () => void }) {
  const { submitTask } = useTasksStore()
  const [input, setInput]     = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent]       = useState(false)

  const submit = async () => {
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)
    try {
      await submitTask(text)
      setSent(true)
      setTimeout(onClose, 900)
    } catch { /* error surfaced via store */ }
    setSending(false)
  }

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.overlay}
      >
        <View style={[styles.sheet, styles.runSheet]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.runTitle}>RUN NEW TASK</Text>
          <Text style={styles.runSub}>Describe what the AI workforce should do</Text>

          <TextInput
            style={styles.runInput}
            value={input}
            onChangeText={setInput}
            placeholder="e.g. Analyze top 10 leads and draft outreach emails…"
            placeholderTextColor={Colors.textDim}
            multiline
            maxLength={1000}
            autoFocus
          />

          <View style={styles.runActions}>
            <TouchableOpacity style={styles.cancelBtn} onPress={onClose}>
              <Text style={styles.cancelBtnText}>CANCEL</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.submitBtn, (!input.trim() || sending || sent) && styles.submitBtnDisabled]}
              onPress={submit}
              disabled={!input.trim() || sending || sent}
            >
              {sending
                ? <ActivityIndicator color={Colors.bg} size="small" />
                : <Text style={styles.submitBtnText}>{sent ? 'QUEUED ✓' : 'RUN TASK'}</Text>
              }
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function TasksScreen() {
  const { tasks, isLoading, fetchTasks, updateTaskFromWs } = useTasksStore()
  const [selected, setSelected] = useState<Task | null>(null)
  const [showRun, setShowRun]   = useState(false)

  useEffect(() => { fetchTasks() }, [])

  useWebSocketEvents(
    ['task:progress', 'task:completed', 'task:update'],
    useCallback((_event, data) => {
      const d = data as Partial<Task> & { id: string }
      if (d?.id) updateTaskFromWs(d)
    }, [updateTaskFromWs]),
  )

  const onRefresh = useCallback(() => fetchTasks(), [fetchTasks])

  const running  = tasks.filter(t => t.status === 'running' || t.status === 'executing').length
  const done     = tasks.filter(t => t.status === 'completed' || t.status === 'success').length
  const failed   = tasks.filter(t => t.status === 'failed' || t.status === 'error').length

  return (
    <View style={styles.page}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <Text style={styles.topTitle}>TASKS</Text>
        <View style={styles.topStats}>
          <Text style={[styles.topStat, { color: Colors.cyan }]}>{running} RUNNING</Text>
          <Text style={styles.topStatDot}>·</Text>
          <Text style={[styles.topStat, { color: Colors.green }]}>{done} DONE</Text>
          <Text style={styles.topStatDot}>·</Text>
          <Text style={[styles.topStat, { color: Colors.red }]}>{failed} FAILED</Text>
        </View>
      </View>

      <FlatList
        data={tasks}
        keyExtractor={t => t.id}
        renderItem={({ item }) => (
          <TaskRow task={item} onPress={() => setSelected(item)} />
        )}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={onRefresh} tintColor={Colors.gold} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>{isLoading ? 'Loading…' : 'No tasks yet'}</Text>
          </View>
        }
      />

      {/* FAB */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); setShowRun(true) }}
        activeOpacity={0.85}
      >
        <Text style={styles.fabText}>+ RUN</Text>
      </TouchableOpacity>

      <TaskDetailModal task={selected} onClose={() => setSelected(null)} />
      {showRun && <RunTaskSheet onClose={() => setShowRun(false)} />}
    </View>
  )
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: Colors.bg },

  topBar: {
    paddingHorizontal: 16, paddingTop: 12, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgDeep,
  },
  topTitle: { fontFamily: Fonts.mono, fontSize: 12, color: Colors.gold, letterSpacing: 3 },
  topStats: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  topStat:  { fontFamily: Fonts.mono, fontSize: 8, fontWeight: '700' },
  topStatDot: { color: Colors.border },

  list: { padding: 10, paddingBottom: 90, gap: 8 },

  taskRow: {
    backgroundColor: Colors.surface1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, padding: 12,
  },
  taskHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  statusDot:  { width: 6, height: 6, borderRadius: 3, marginRight: 8 },
  taskTitle:  { flex: 1, fontFamily: Fonts.mono, fontSize: 11, color: Colors.text },
  statusBadge:{ fontFamily: Fonts.mono, fontSize: 7, fontWeight: '700' },
  agentLabel: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.gold, marginBottom: 6 },
  track: { height: 2, backgroundColor: Colors.border, borderRadius: 1, marginVertical: 4 },
  bar:   { height: 2, borderRadius: 1 },
  pctLabel: { fontFamily: Fonts.mono, fontSize: 7, color: Colors.textDim, textAlign: 'right' },

  empty:     { flex: 1, alignItems: 'center', padding: 60 },
  emptyText: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.textDim },

  fab: {
    position: 'absolute', bottom: 24, right: 20,
    backgroundColor: Colors.gold, borderRadius: 24,
    paddingHorizontal: 20, paddingVertical: 12,
    shadowColor: Colors.gold, shadowOpacity: 0.4, shadowRadius: 12, shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  fabText: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.bg, fontWeight: '700', letterSpacing: 1 },

  // Modal overlay
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: Colors.bgDeep,
    borderTopLeftRadius: 16, borderTopRightRadius: 16,
    borderWidth: 1, borderColor: Colors.border, borderBottomWidth: 0,
    maxHeight: '80%',
  },
  sheetHandle: {
    width: 36, height: 4, backgroundColor: Colors.border,
    borderRadius: 2, alignSelf: 'center', marginTop: 10, marginBottom: 8,
  },
  sheetHeader: {
    flexDirection: 'row', alignItems: 'flex-start',
    paddingHorizontal: 16, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  sheetTitle: { flex: 1, fontFamily: Fonts.mono, fontSize: 13, color: Colors.text },
  closeBtn:   { padding: 4, marginLeft: 8 },
  closeBtnText: { fontSize: 14, color: Colors.textDim },
  sheetScroll: { },
  sheetContent: { padding: 16, gap: 10 },

  detailRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 4 },
  detailKey: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1 },
  detailVal: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.text },

  resultBox: {
    backgroundColor: Colors.surface2, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 6, padding: 10, marginTop: 8,
  },
  resultBoxError: { borderColor: `${Colors.red}40` },
  resultLabel: { fontFamily: Fonts.mono, fontSize: 8, color: Colors.textDim, letterSpacing: 1, marginBottom: 6 },
  resultText:  { fontFamily: Fonts.mono, fontSize: 10, color: Colors.textMuted, lineHeight: 16 },

  // Run task sheet
  runSheet: { paddingHorizontal: 16, paddingBottom: 24, maxHeight: '70%' },
  runTitle: { fontFamily: Fonts.mono, fontSize: 13, color: Colors.gold, letterSpacing: 2, marginBottom: 4 },
  runSub:   { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, marginBottom: 14 },
  runInput: {
    backgroundColor: Colors.surface1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, padding: 12, color: Colors.text, fontFamily: Fonts.mono,
    fontSize: 12, minHeight: 100, textAlignVertical: 'top',
  },
  runActions: { flexDirection: 'row', gap: 10, marginTop: 14 },
  cancelBtn: {
    flex: 1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, paddingVertical: 12, alignItems: 'center',
  },
  cancelBtnText: { fontFamily: Fonts.mono, fontSize: 10, color: Colors.textMuted },
  submitBtn: {
    flex: 2, backgroundColor: Colors.gold,
    borderRadius: 8, paddingVertical: 12, alignItems: 'center',
  },
  submitBtnDisabled: { opacity: 0.4 },
  submitBtnText: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.bg, fontWeight: '700', letterSpacing: 1 },
})
