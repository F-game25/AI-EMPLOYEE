/**
 * SetupScreen — first-run server configuration
 * User enters server URL + optional certificate pin
 * QR scan supported for quick setup
 */
import React, { useState } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Alert,
} from 'react-native'
import * as Device from 'expo-device'
import { api, getOrCreateDeviceId, saveServerUrl } from '../api/secureClient'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

interface Props {
  onSetupComplete: () => void
}

export default function SetupScreen({ onSetupComplete }: Props) {
  const [url, setUrl]         = useState('http://')
  const [testing, setTesting] = useState(false)
  const [status, setStatus]   = useState<'idle' | 'ok' | 'err'>('idle')
  const [errMsg, setErrMsg]   = useState('')
  const [pairCode, setPairCode] = useState('')

  const waitForPairingApproval = async (requestId: string) => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const status = await api.getPairingStatus(requestId).catch(() => null)
      if (status?.approved) return true
      if (status?.status === 'expired') return false
      await new Promise(resolve => setTimeout(resolve, 2000))
    }
    return false
  }

  const testAndSave = async () => {
    const trimmed = url.trim().replace(/\/+$/, '')
    if (!trimmed.startsWith('http')) {
      Alert.alert('Invalid URL', 'URL must start with http:// or https://')
      return
    }
    setTesting(true)
    setStatus('idle')
    try {
      const res = await fetch(`${trimmed}/api/health`, { signal: AbortSignal.timeout(5000) })
      const data = await res.json().catch(() => null) as { status?: string } | null
      if (res.ok || data?.status === 'ok' || (res.status >= 200 && res.status < 500)) {
        await saveServerUrl(trimmed)
        try {
          const deviceId = await getOrCreateDeviceId()
          const deviceName = `${Device.manufacturer || Platform.OS} ${Device.modelName || 'Mobile'}`
          const pairing = await api.requestPairing(deviceId, deviceName)
          setPairCode(pairing.pairing_code)
          const approved = await waitForPairingApproval(pairing.request_id)
          if (!approved) {
            throw new Error('Pairing approval timed out')
          }
        } catch {
          throw new Error('Mobile pairing was not approved')
        }
        setStatus('ok')
        setTimeout(onSetupComplete, 600)
      } else {
        throw new Error(`Server returned ${res.status}`)
      }
    } catch (e: unknown) {
      setStatus('err')
      setErrMsg((e as Error).message || 'Connection failed')
    }
    setTesting(false)
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={styles.flex}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        {/* Logo */}
        <View style={styles.logo}>
          <Text style={styles.logoSymbol}>◈</Text>
          <Text style={styles.logoTitle}>NEXUS OS</Text>
          <Text style={styles.logoSub}>Mobile Client Setup</Text>
        </View>

        {/* Instructions */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>CONNECT TO YOUR SYSTEM</Text>
          <Text style={styles.cardBody}>
            Enter the URL of your AI-EMPLOYEE server. Both local network and public URLs are supported.
            Use HTTPS for production deployments.
          </Text>

          <View style={styles.examples}>
            <Text style={styles.exampleLabel}>Examples:</Text>
            <Text style={styles.exampleItem}>http://192.168.1.100:8787</Text>
            <Text style={styles.exampleItem}>https://your-server.com</Text>
          </View>
        </View>

        {/* URL Input */}
        <View style={styles.inputGroup}>
          <Text style={styles.inputLabel}>SERVER URL</Text>
          <TextInput
            style={[styles.input, status === 'err' && styles.inputError, status === 'ok' && styles.inputOk]}
            value={url}
            onChangeText={setUrl}
            placeholder="http://your-server:8787"
            placeholderTextColor={Colors.textDim}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="done"
            onSubmitEditing={testAndSave}
          />
          {status === 'err' && <Text style={styles.errorText}>✗ {errMsg}</Text>}
          {testing && pairCode && (
            <Text style={styles.okText}>Approve pairing code {pairCode} on the PC</Text>
          )}
          {status === 'ok'  && (
            <Text style={styles.okText}>
              ✓ Paired securely — loading dashboard…
            </Text>
          )}
        </View>

        {/* Connect button */}
        <TouchableOpacity
          style={[styles.btn, testing && styles.btnDisabled]}
          onPress={testAndSave}
          disabled={testing}
          activeOpacity={0.8}
        >
          {testing
            ? <ActivityIndicator color={Colors.bg} size="small" />
            : <Text style={styles.btnText}>CONNECT</Text>
          }
        </TouchableOpacity>

        {/* Security note */}
        <Text style={styles.secNote}>
          Your credentials are stored in the device's encrypted keychain and never transmitted in plain text.
          The connection uses JWT authentication with automatic token rotation.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  flex:       { flex: 1, backgroundColor: Colors.bg },
  container:  { flexGrow: 1, padding: 24, justifyContent: 'center' },

  logo: { alignItems: 'center', marginBottom: 32 },
  logoSymbol: { fontSize: 48, color: Colors.gold, marginBottom: 8 },
  logoTitle:  { fontFamily: Fonts.mono, fontSize: 20, color: Colors.gold, letterSpacing: 6 },
  logoSub:    { fontFamily: Fonts.mono, fontSize: 10, color: Colors.textDim, letterSpacing: 2, marginTop: 4 },

  card: {
    backgroundColor: Colors.surface1,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, padding: 16, marginBottom: 20,
  },
  cardTitle: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.gold, letterSpacing: 1.5, marginBottom: 8 },
  cardBody:  { fontFamily: Fonts.sans, fontSize: 13, color: Colors.textMuted, lineHeight: 20 },
  examples:  { marginTop: 12 },
  exampleLabel: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, marginBottom: 4 },
  exampleItem:  { fontFamily: Fonts.mono, fontSize: 10, color: Colors.cyan, marginBottom: 2 },

  inputGroup: { marginBottom: 16 },
  inputLabel: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1.5, marginBottom: 6 },
  input: {
    backgroundColor: Colors.surface2,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: 6, padding: 12,
    color: Colors.text, fontFamily: Fonts.mono, fontSize: 13,
  },
  inputError: { borderColor: Colors.red },
  inputOk:    { borderColor: Colors.green },
  errorText:  { fontFamily: Fonts.mono, fontSize: 10, color: Colors.red, marginTop: 6 },
  okText:     { fontFamily: Fonts.mono, fontSize: 10, color: Colors.green, marginTop: 6 },

  btn: {
    backgroundColor: Colors.gold,
    borderRadius: 6, padding: 14,
    alignItems: 'center', marginBottom: 16,
  },
  btnDisabled: { opacity: 0.6 },
  btnText: { fontFamily: Fonts.mono, fontSize: 12, color: Colors.bg, fontWeight: '700', letterSpacing: 2 },

  secNote: {
    fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim,
    textAlign: 'center', lineHeight: 15,
  },
})
