import React, { useEffect, useState, useRef } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  RefreshControl, FlatList,
} from 'react-native'
import * as Haptics from 'expo-haptics'
import { api, ws } from '../api/secureClient'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

interface Threat { ip: string; path: string; reason: string; score: number; ts: number }
interface BlockedIP { ip: string; reason: string; blocked_at: number }
interface AuditEntry { id: string; actor: string; action: string; resource: string; ts: number }

const SEV_COLOR = (score: number) =>
  score >= 80 ? Colors.red : score >= 50 ? Colors.orange : Colors.gold

function ThreatRow({ t }: { t: Threat }) {
  const col = SEV_COLOR(t.score)
  return (
    <View style={[styles.row, { borderLeftColor: col }]}>
      <Text style={[styles.cell, styles.cellIp]}>{t.ip}</Text>
      <Text style={[styles.cell, { flex: 1 }]} numberOfLines={1}>{t.path}</Text>
      <Text style={[styles.cellScore, { color: col }]}>{t.score}</Text>
    </View>
  )
}

function BlockedRow({ b, onUnblock }: { b: BlockedIP; onUnblock: (ip: string) => void }) {
  return (
    <View style={styles.row}>
      <Text style={[styles.cell, styles.cellIp]}>{b.ip}</Text>
      <Text style={[styles.cell, { flex: 1 }]} numberOfLines={1}>{b.reason}</Text>
      <TouchableOpacity style={styles.unblockBtn} onPress={() => onUnblock(b.ip)}>
        <Text style={styles.unblockText}>UNBLOCK</Text>
      </TouchableOpacity>
    </View>
  )
}

function AuditRow({ e }: { e: AuditEntry }) {
  return (
    <View style={styles.row}>
      <Text style={[styles.cell, styles.cellActor]}>{e.actor}</Text>
      <Text style={[styles.cell, { flex: 1 }]} numberOfLines={1}>{e.action}</Text>
      <Text style={[styles.cellTs]}>{new Date(e.ts).toLocaleTimeString()}</Text>
    </View>
  )
}

type Tab = 'threats' | 'blocked' | 'audit'

export default function SecurityScreen() {
  const [tab, setTab]           = useState<Tab>('threats')
  const [threats, setThreats]   = useState<Threat[]>([])
  const [blocked, setBlocked]   = useState<BlockedIP[]>([])
  const [audit, setAudit]       = useState<AuditEntry[]>([])
  const [score, setScore]       = useState(0)
  const [loading, setLoading]   = useState(false)
  const [strictMode, setStrict] = useState(false)
  const scoreColor = SEV_COLOR(score)

  const load = async () => {
    setLoading(true)
    try {
      const [t, b, a, s] = await Promise.allSettled([
        api.get('/api/security/threats'),
        api.get('/api/security/blocked-ips'),
        api.get('/api/security/audit?limit=50'),
        api.get('/api/security/status'),
      ])
      if (t.status === 'fulfilled') {
        const d = t.value as { threats?: Threat[]; score?: number }
        setThreats(d.threats || [])
        setScore(d.score || 0)
      }
      if (b.status === 'fulfilled') setBlocked((b.value as { blocked_ips?: BlockedIP[] }).blocked_ips || [])
      if (a.status === 'fulfilled') setAudit((a.value as { entries?: AuditEntry[] }).entries || [])
      if (s.status === 'fulfilled') setStrict((s.value as { strict_mode?: boolean }).strict_mode || false)
    } catch { /* empty */ }
    setLoading(false)
  }

  useEffect(() => {
    load()
    const unsub = ws.on('security:breach', () => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error)
      load()
    })
    return () => { unsub() }
  }, [])

  const unblock = async (ip: string) => {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)
    try {
      await api.post('/api/security/blocked-ips/unblock', { ip })
      setBlocked(prev => prev.filter(b => b.ip !== ip))
    } catch { /* empty */ }
  }

  const toggleStrict = async () => {
    const next = !strictMode
    try {
      await api.post('/api/security/strict-mode', { enabled: next })
      setStrict(next)
    } catch { /* empty */ }
  }

  const rotateJWT = async () => {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy)
    try {
      await api.post('/api/security/rotate-jwt', {})
    } catch { /* empty */ }
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: 'threats', label: 'THREATS' },
    { id: 'blocked', label: 'BLOCKED' },
    { id: 'audit',   label: 'AUDIT' },
  ]

  return (
    <View style={styles.page}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.scoreBlock}>
          <Text style={[styles.scoreNum, { color: scoreColor }]}>{score}</Text>
          <Text style={styles.scoreLabel}>THREAT SCORE</Text>
        </View>
        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.actionBtn, strictMode && styles.actionBtnActive]}
            onPress={toggleStrict}
          >
            <Text style={[styles.actionBtnText, strictMode && { color: Colors.red }]}>
              {strictMode ? 'STRICT ON' : 'STRICT OFF'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={rotateJWT}>
            <Text style={styles.actionBtnText}>ROTATE JWT</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        {TABS.map(t => (
          <TouchableOpacity
            key={t.id}
            style={[styles.tabBtn, tab === t.id && styles.tabBtnActive]}
            onPress={() => setTab(t.id)}
          >
            <Text style={[styles.tabBtnText, tab === t.id && styles.tabBtnTextActive]}>
              {t.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Content */}
      <ScrollView
        style={styles.scroll}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.purple} />}
      >
        {tab === 'threats' && (
          threats.length === 0
            ? <Text style={styles.empty}>No active threats detected</Text>
            : threats.map((t, i) => <ThreatRow key={i} t={t} />)
        )}
        {tab === 'blocked' && (
          blocked.length === 0
            ? <Text style={styles.empty}>No blocked IPs</Text>
            : blocked.map((b, i) => <BlockedRow key={i} b={b} onUnblock={unblock} />)
        )}
        {tab === 'audit' && (
          audit.length === 0
            ? <Text style={styles.empty}>No audit entries</Text>
            : audit.map((e) => <AuditRow key={e.id} e={e} />)
        )}
      </ScrollView>
    </View>
  )
}

const styles = StyleSheet.create({
  page:   { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: 14, borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgDeep,
  },
  scoreBlock: { alignItems: 'flex-start' },
  scoreNum:   { fontFamily: Fonts.mono, fontSize: 36, fontWeight: '700', lineHeight: 38 },
  scoreLabel: { fontFamily: Fonts.mono, fontSize: 8, color: Colors.textDim, letterSpacing: 1.5, marginTop: 2 },
  actions:    { gap: 8 },
  actionBtn:  {
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: 4, paddingHorizontal: 10, paddingVertical: 6,
  },
  actionBtnActive: { borderColor: Colors.red },
  actionBtnText:   { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textMuted },

  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: Colors.border },
  tabBtn: { flex: 1, padding: 10, alignItems: 'center' },
  tabBtnActive: { borderBottomWidth: 2, borderBottomColor: Colors.purple },
  tabBtnText: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1 },
  tabBtnTextActive: { color: Colors.purple },

  scroll: { flex: 1 },
  row: {
    flexDirection: 'row', alignItems: 'center',
    borderLeftWidth: 2, borderLeftColor: Colors.border,
    paddingHorizontal: 12, paddingVertical: 8,
    borderBottomWidth: 1, borderBottomColor: Colors.borderFaint,
  },
  cell:       { fontFamily: Fonts.mono, fontSize: 10, color: Colors.textMuted },
  cellIp:     { width: 110, color: Colors.text },
  cellScore:  { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '700', width: 36, textAlign: 'right' },
  cellActor:  { width: 80, color: Colors.gold },
  cellTs:     { fontFamily: Fonts.mono, fontSize: 8, color: Colors.textDim, width: 60, textAlign: 'right' },
  unblockBtn: { borderWidth: 1, borderColor: Colors.red, borderRadius: 3, paddingHorizontal: 6, paddingVertical: 3 },
  unblockText:{ fontFamily: Fonts.mono, fontSize: 8, color: Colors.red },
  empty:      { fontFamily: Fonts.mono, fontSize: 11, color: Colors.textDim, textAlign: 'center', padding: 40 },
})
