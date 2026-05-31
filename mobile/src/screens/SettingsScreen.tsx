import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  ActivityIndicator, Alert,
} from 'react-native'
import * as Clipboard from 'expo-clipboard'
import { api, getServerUrl } from '../api/secureClient'
import { useAuthStore } from '../store/authStore'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

// ── Types ────────────────────────────────────────────────────────────────────

interface SessionsResponse {
  sessions: unknown[]
  count:    number
}

interface ApiKeyResponse {
  key: string
}

// ── Sub-components ───────────────────────────────────────────────────────────

function InfoRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoKey}>{label}</Text>
      <Text style={[styles.infoVal, color ? { color } : null]} numberOfLines={1}>{value}</Text>
    </View>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function SettingsScreen() {
  const { user, logout } = useAuthStore()

  const [serverUrl,      setServerUrl]      = useState<string | null>(null)
  const [sessionCount,   setSessionCount]   = useState<number | null>(null)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [revoking,       setRevoking]       = useState(false)
  const [keyLoading,     setKeyLoading]     = useState(false)

  // Load server URL + session count on mount
  useEffect(() => {
    getServerUrl().then(url => setServerUrl(url))
    fetchSessions()
  }, [])

  const fetchSessions = useCallback(async () => {
    setSessionsLoading(true)
    try {
      const data = await api.get<SessionsResponse>('/api/sessions')
      setSessionCount(data.count ?? data.sessions?.length ?? 0)
    } catch {
      setSessionCount(null)
    } finally {
      setSessionsLoading(false)
    }
  }, [])

  const revokeOtherSessions = useCallback(async () => {
    Alert.alert(
      'Revoke Sessions',
      'This will sign out all other devices. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Revoke',
          style: 'destructive',
          onPress: async () => {
            setRevoking(true)
            try {
              await api.del('/api/sessions')
              await fetchSessions()
              Alert.alert('Done', 'All other sessions revoked.')
            } catch (e: unknown) {
              Alert.alert('Error', (e as { message?: string }).message ?? 'Failed to revoke sessions')
            } finally {
              setRevoking(false)
            }
          },
        },
      ],
    )
  }, [fetchSessions])

  const generateApiKey = useCallback(async () => {
    setKeyLoading(true)
    try {
      const data = await api.post<ApiKeyResponse>('/api/api-keys')
      const key  = data.key
      await Clipboard.setStringAsync(key)
      Alert.alert(
        'API Key Generated',
        `Your new key (copied to clipboard):\n\n${key}\n\nStore it securely — it will not be shown again.`,
        [{ text: 'OK' }],
      )
    } catch (e: unknown) {
      Alert.alert('Error', (e as { message?: string }).message ?? 'Key generation failed')
    } finally {
      setKeyLoading(false)
    }
  }, [])

  const confirmLogout = useCallback(() => {
    Alert.alert('Sign Out', 'Sign out of this device?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign Out', style: 'destructive', onPress: () => logout() },
    ])
  }, [logout])

  return (
    <View style={styles.page}>
      <View style={styles.topBar}>
        <Text style={styles.topTitle}>SETTINGS</Text>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>

        {/* Server */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>SERVER</Text>
          <InfoRow label="URL" value={serverUrl ?? 'Not configured'} color={serverUrl ? Colors.cyan : Colors.textDim} />
        </View>

        {/* Account */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>ACCOUNT</Text>
          <InfoRow label="EMAIL"     value={user?.email     ?? '—'} />
          <InfoRow label="ROLE"      value={user?.role      ?? '—'} color={Colors.gold} />
          <InfoRow label="TENANT"    value={user?.tenant_id ?? '—'} color={Colors.cyan} />
        </View>

        {/* Sessions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>ACTIVE SESSIONS</Text>
          <View style={styles.sessionRow}>
            <View style={styles.sessionLeft}>
              <Text style={styles.infoKey}>SESSIONS</Text>
              {sessionsLoading ? (
                <ActivityIndicator color={Colors.gold} size="small" style={styles.sessionSpinner} />
              ) : (
                <View style={styles.countBadge}>
                  <Text style={styles.countText}>{sessionCount ?? '?'}</Text>
                </View>
              )}
            </View>
            <TouchableOpacity
              style={[styles.actionBtn, revoking && styles.actionBtnDisabled]}
              onPress={revokeOtherSessions}
              disabled={revoking}
            >
              {revoking
                ? <ActivityIndicator color={Colors.text} size="small" />
                : <Text style={styles.actionBtnText}>REVOKE ALL OTHER</Text>
              }
            </TouchableOpacity>
          </View>
        </View>

        {/* API Keys */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>API ACCESS</Text>
          <Text style={styles.helpText}>
            Generate a key for direct API access. Keys are shown once — copy immediately.
          </Text>
          <TouchableOpacity
            style={[styles.actionBtn, styles.actionBtnFull, keyLoading && styles.actionBtnDisabled]}
            onPress={generateApiKey}
            disabled={keyLoading}
          >
            {keyLoading
              ? <ActivityIndicator color={Colors.text} size="small" />
              : <Text style={styles.actionBtnText}>GENERATE API KEY</Text>
            }
          </TouchableOpacity>
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutBtn} onPress={confirmLogout} activeOpacity={0.8}>
          <Text style={styles.logoutBtnText}>SIGN OUT</Text>
        </TouchableOpacity>

      </ScrollView>
    </View>
  )
}

const styles = StyleSheet.create({
  page:   { flex: 1, backgroundColor: Colors.bg },

  topBar: {
    paddingHorizontal: 16, paddingTop: 12, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgDeep,
  },
  topTitle: { fontFamily: Fonts.mono, fontSize: 12, color: Colors.gold, letterSpacing: 3 },

  scroll:        { flex: 1 },
  scrollContent: { padding: 12, gap: 12, paddingBottom: 40 },

  section: {
    backgroundColor: Colors.surface1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, padding: 14,
  },
  sectionTitle: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1.5, marginBottom: 10 },

  infoRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: Colors.borderFaint,
  },
  infoKey: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1 },
  infoVal: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.text, maxWidth: '65%', textAlign: 'right' },

  sessionRow:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sessionLeft:   { flexDirection: 'row', alignItems: 'center', gap: 10 },
  sessionSpinner:{ marginLeft: 8 },

  countBadge: {
    backgroundColor: Colors.goldGlow, borderWidth: 1, borderColor: Colors.borderGold,
    borderRadius: 12, paddingHorizontal: 10, paddingVertical: 2,
  },
  countText: { fontFamily: Fonts.mono, fontSize: 12, color: Colors.gold, fontWeight: '700' },

  helpText: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, lineHeight: 14, marginBottom: 12 },

  actionBtn: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: 6,
    paddingHorizontal: 12, paddingVertical: 8, alignItems: 'center', justifyContent: 'center',
  },
  actionBtnFull:     { width: '100%' },
  actionBtnDisabled: { opacity: 0.5 },
  actionBtnText:     { fontFamily: Fonts.mono, fontSize: 9, color: Colors.text, letterSpacing: 1 },

  logoutBtn: {
    backgroundColor: `${Colors.red}15`, borderWidth: 1, borderColor: `${Colors.red}40`,
    borderRadius: 8, paddingVertical: 14, alignItems: 'center', marginTop: 4,
  },
  logoutBtnText: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.red, fontWeight: '700', letterSpacing: 1.5 },
})
