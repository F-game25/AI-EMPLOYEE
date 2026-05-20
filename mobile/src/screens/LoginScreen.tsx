import React, { useState } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native'
import * as LocalAuthentication from 'expo-local-authentication'
import * as Haptics from 'expo-haptics'
import { useAuthStore } from '../store/authStore'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

export default function LoginScreen() {
  const { login, isLoading, error, clearError } = useAuthStore()
  const [email, setEmail]     = useState('')
  const [password, setPassword] = useState('')

  const handleLogin = async () => {
    if (!email || !password) return
    clearError()
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)
    await login(email, password)
  }

  const handleBiometric = async () => {
    const compatible = await LocalAuthentication.hasHardwareAsync()
    if (!compatible) return Alert.alert('Biometrics not available')
    const enrolled = await LocalAuthentication.isEnrolledAsync()
    if (!enrolled) return Alert.alert('No biometrics enrolled', 'Add Face ID or fingerprint in device settings.')
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: 'Authenticate to access NEXUS OS',
      fallbackLabel:  'Use passcode',
    })
    if (result.success) {
      // Biometric success — use stored credentials
      // In production: retrieve stored credentials from secure store after biometric unlock
      Alert.alert('Biometric auth', 'Enter credentials to link biometric login on first use.')
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={styles.flex}
    >
      <View style={styles.container}>
        {/* Eye logo */}
        <View style={styles.logo}>
          <Text style={styles.eye}>◉</Text>
          <Text style={styles.title}>NEXUS OS</Text>
          <Text style={styles.sub}>AI OPERATING SYSTEM</Text>
        </View>

        {/* Fields */}
        <View style={styles.form}>
          <Text style={styles.label}>EMAIL</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            placeholder="admin@example.com"
            placeholderTextColor={Colors.textDim}
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
          />

          <Text style={[styles.label, { marginTop: 14 }]}>PASSWORD</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor={Colors.textDim}
            secureTextEntry
            returnKeyType="done"
            onSubmitEditing={handleLogin}
          />

          {error && <Text style={styles.error}>✗ {error}</Text>}

          <TouchableOpacity
            style={[styles.loginBtn, isLoading && styles.btnDisabled]}
            onPress={handleLogin}
            disabled={isLoading}
            activeOpacity={0.8}
          >
            {isLoading
              ? <ActivityIndicator color={Colors.bg} />
              : <Text style={styles.loginBtnText}>AUTHENTICATE</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity style={styles.bioBtn} onPress={handleBiometric} activeOpacity={0.7}>
            <Text style={styles.bioBtnText}>⬡ Use Biometrics</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.footer}>
          All data encrypted in transit · JWT auth · Auto token rotation
        </Text>
      </View>
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  flex:      { flex: 1, backgroundColor: Colors.bg },
  container: { flex: 1, padding: 28, justifyContent: 'center' },

  logo:  { alignItems: 'center', marginBottom: 40 },
  eye:   { fontSize: 56, color: Colors.gold, marginBottom: 12 },
  title: { fontFamily: Fonts.mono, fontSize: 18, color: Colors.gold, letterSpacing: 6, fontWeight: '700' },
  sub:   { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 3, marginTop: 4 },

  form:  { width: '100%' },
  label: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, letterSpacing: 1.5, marginBottom: 6 },
  input: {
    backgroundColor: Colors.surface1,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: 6, padding: 14,
    color: Colors.text, fontFamily: Fonts.mono, fontSize: 13,
  },

  error: { fontFamily: Fonts.mono, fontSize: 10, color: Colors.red, marginTop: 10 },

  loginBtn: {
    backgroundColor: Colors.gold,
    borderRadius: 6, padding: 15,
    alignItems: 'center', marginTop: 20,
  },
  btnDisabled:   { opacity: 0.6 },
  loginBtnText:  { fontFamily: Fonts.mono, fontSize: 12, color: Colors.bg, fontWeight: '700', letterSpacing: 2 },

  bioBtn: {
    alignItems: 'center', padding: 12, marginTop: 10,
    borderWidth: 1, borderColor: Colors.border, borderRadius: 6,
  },
  bioBtnText: { fontFamily: Fonts.mono, fontSize: 11, color: Colors.textMuted },

  footer: {
    fontFamily: Fonts.mono, fontSize: 8, color: Colors.textDim,
    textAlign: 'center', marginTop: 40, lineHeight: 14,
  },
})
