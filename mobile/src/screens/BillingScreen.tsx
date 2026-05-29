import React, { useEffect, useState, useCallback, useRef } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  RefreshControl, ActivityIndicator, Linking,
} from 'react-native'
import { api, getServerUrl } from '../api/secureClient'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

// ── Types ────────────────────────────────────────────────────────────────────

interface BillingSummary {
  daily_spend:    number
  monthly_spend:  number
  daily_limit:    number
  monthly_limit:  number
  status:         'ok' | 'warning' | 'hard_cap'
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function pct(spend: number, limit: number): number {
  if (!limit) return 0
  return Math.min(100, Math.max(0, (spend / limit) * 100))
}

function barColor(p: number): string {
  if (p >= 90) return Colors.red
  if (p >= 60) return Colors.warning
  return Colors.green
}

function fmt(n: number): string {
  return n >= 1000 ? `$${(n / 1000).toFixed(2)}k` : `$${n.toFixed(2)}`
}

// ── Sub-components ───────────────────────────────────────────────────────────

function SpendRow({
  label, spend, limit,
}: { label: string; spend: number; limit: number }) {
  const p    = pct(spend, limit)
  const col  = barColor(p)
  return (
    <View style={styles.spendRow}>
      <View style={styles.spendMeta}>
        <Text style={styles.spendLabel}>{label}</Text>
        <Text style={[styles.spendValue, { color: col }]}>
          {fmt(spend)} <Text style={styles.spendLimit}>/ {fmt(limit)}</Text>
        </Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.bar, { width: `${p}%` as `${number}%`, backgroundColor: col }]} />
      </View>
      <Text style={[styles.pctText, { color: col }]}>{p.toFixed(1)}%</Text>
    </View>
  )
}

function StatusBadge({ status }: { status: BillingSummary['status'] }) {
  const map = {
    ok:       { label: 'OK',       bg: `${Colors.green}20`,   text: Colors.green },
    warning:  { label: 'WARNING',  bg: `${Colors.warning}20`, text: Colors.warning },
    hard_cap: { label: 'HARD CAP', bg: `${Colors.red}20`,     text: Colors.red },
  }
  const s = map[status] ?? map.ok
  return (
    <View style={[styles.badge, { backgroundColor: s.bg }]}>
      <Text style={[styles.badgeText, { color: s.text }]}>{s.label}</Text>
    </View>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function BillingScreen() {
  const [summary,   setSummary]   = useState<BillingSummary | null>(null)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchSummary = useCallback(async () => {
    try {
      const data = await api.get<BillingSummary>('/api/billing/summary')
      setSummary(data)
      setError(null)
    } catch (e: unknown) {
      setError((e as { message?: string }).message ?? 'Failed to load billing')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSummary()
    intervalRef.current = setInterval(fetchSummary, 60_000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [fetchSummary])

  const onRefresh = useCallback(async () => {
    setLoading(true)
    await fetchSummary()
  }, [fetchSummary])

  const openStripe = useCallback(async () => {
    const base = await getServerUrl()
    if (base) await Linking.openURL(`${base}/api/billing/stripe/checkout`)
  }, [])

  return (
    <View style={styles.page}>
      <View style={styles.topBar}>
        <Text style={styles.topTitle}>BILLING</Text>
        {summary && <StatusBadge status={summary.status} />}
      </View>

      {loading && !summary ? (
        <View style={styles.center}>
          <ActivityIndicator color={Colors.gold} size="large" />
          <Text style={styles.loadingText}>Loading billing data…</Text>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={onRefresh}>
            <Text style={styles.retryBtnText}>RETRY</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={onRefresh} tintColor={Colors.gold} />}
        >
          {/* Spend cards */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>SPEND OVERVIEW</Text>

            {summary && (
              <>
                <SpendRow
                  label="TODAY"
                  spend={summary.daily_spend}
                  limit={summary.daily_limit}
                />
                <View style={styles.divider} />
                <SpendRow
                  label="THIS MONTH"
                  spend={summary.monthly_spend}
                  limit={summary.monthly_limit}
                />
              </>
            )}
          </View>

          {/* Limits */}
          {summary && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>LIMITS</Text>
              <View style={styles.limitRow}>
                <Text style={styles.limitKey}>DAILY LIMIT</Text>
                <Text style={styles.limitVal}>{fmt(summary.daily_limit)}</Text>
              </View>
              <View style={styles.limitRow}>
                <Text style={styles.limitKey}>MONTHLY LIMIT</Text>
                <Text style={styles.limitVal}>{fmt(summary.monthly_limit)}</Text>
              </View>
            </View>
          )}

          {/* Manage button */}
          <TouchableOpacity style={styles.manageBtn} onPress={openStripe} activeOpacity={0.8}>
            <Text style={styles.manageBtnText}>MANAGE BILLING</Text>
          </TouchableOpacity>

          <Text style={styles.hint}>Opens Stripe billing portal in browser</Text>
        </ScrollView>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  page:   { flex: 1, backgroundColor: Colors.bg },

  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: 12, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgDeep,
  },
  topTitle: { fontFamily: Fonts.mono, fontSize: 12, color: Colors.gold, letterSpacing: 3 },

  badge: { borderRadius: 4, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { fontFamily: Fonts.mono, fontSize: 8, fontWeight: '700', letterSpacing: 1 },

  center:      { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingText: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.textDim },
  errorText:   { fontFamily: Fonts.mono, fontSize: 11, color: Colors.red, textAlign: 'center', paddingHorizontal: 24 },

  retryBtn:     { borderWidth: 1, borderColor: Colors.border, borderRadius: 6, paddingHorizontal: 16, paddingVertical: 8 },
  retryBtnText: { fontFamily: Fonts.mono, fontSize: 10, color: Colors.textMuted },

  scroll:        { flex: 1 },
  scrollContent: { padding: 12, gap: 12 },

  section: {
    backgroundColor: Colors.surface1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, padding: 14,
  },
  sectionTitle: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1.5, marginBottom: 12 },
  divider:      { height: 1, backgroundColor: Colors.borderFaint, marginVertical: 10 },

  spendRow:   { gap: 6 },
  spendMeta:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  spendLabel: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1 },
  spendValue: { fontFamily: Fonts.mono, fontSize: 14, fontWeight: '700' },
  spendLimit: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, fontWeight: '400' },
  track:      { height: 4, backgroundColor: Colors.border, borderRadius: 2 },
  bar:        { height: 4, borderRadius: 2 },
  pctText:    { fontFamily: Fonts.mono, fontSize: 8, textAlign: 'right' },

  limitRow:  { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: Colors.borderFaint },
  limitKey:  { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1 },
  limitVal:  { fontFamily: Fonts.mono, fontSize: 11, color: Colors.text },

  manageBtn: {
    backgroundColor: Colors.goldGlow, borderWidth: 1, borderColor: Colors.borderGold,
    borderRadius: 8, paddingVertical: 14, alignItems: 'center',
  },
  manageBtnText: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.gold, fontWeight: '700', letterSpacing: 1.5 },

  hint: { fontFamily: Fonts.mono, fontSize: 8, color: Colors.textDim, textAlign: 'center' },
})
