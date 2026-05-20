import React, { useEffect, useState } from 'react'
import { StatusBar, View, ActivityIndicator, StyleSheet } from 'react-native'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { useAuthStore } from './src/store/authStore'
import { getServerUrl } from './src/api/secureClient'
import AppNavigator from './src/navigation'
import { Colors } from './src/theme/colors'

export default function App() {
  const { user, isLoading: authLoading, checkAuth } = useAuthStore()
  const [bootstrapped, setBootstrapped] = useState(false)
  const [serverReady, setServerReady]   = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        const url = await getServerUrl()
        if (url) {
          setServerReady(true)
          await checkAuth()
        }
      } catch { /* first run */ }
      setBootstrapped(true)
    })()
  }, [])

  const handleSetupDone = async () => {
    setServerReady(true)
    await checkAuth()
  }

  if (!bootstrapped) {
    return (
      <View style={styles.boot}>
        <ActivityIndicator color={Colors.gold} size="large" />
      </View>
    )
  }

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <StatusBar barStyle="light-content" backgroundColor={Colors.bg} />
        <AppNavigator
          serverReady={serverReady}
          authed={user !== null}
          onSetupDone={handleSetupDone}
        />
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.bg },
  boot: { flex: 1, backgroundColor: Colors.bg, alignItems: 'center', justifyContent: 'center' },
})
