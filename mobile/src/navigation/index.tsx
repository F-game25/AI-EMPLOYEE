import React from 'react'
import { NavigationContainer } from '@react-navigation/native'
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs'
import { createNativeStackNavigator } from '@react-navigation/native-stack'
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

import SetupScreen      from '../screens/SetupScreen'
import LoginScreen      from '../screens/LoginScreen'
import DashboardScreen  from '../screens/DashboardScreen'
import AgentsScreen     from '../screens/AgentsScreen'
import SecurityScreen   from '../screens/SecurityScreen'
import ChatScreen       from '../screens/ChatScreen'
import TasksScreen      from '../screens/TasksScreen'
import BillingScreen    from '../screens/BillingScreen'
import SettingsScreen   from '../screens/SettingsScreen'

// ── Param lists ──────────────────────────────────────────────────────────────

export type RootStackParamList = {
  Setup:  undefined
  Login:  undefined
  Main:   undefined
}

export type MainTabParamList = {
  Dashboard: undefined
  Agents:    undefined
  Chat:      undefined
  Security:  undefined
  More:      undefined
}

export type MoreStackParamList = {
  MoreMenu:  undefined
  Tasks:     undefined
  Billing:   undefined
  Settings:  undefined
}

// ── Navigators ───────────────────────────────────────────────────────────────

const Stack    = createNativeStackNavigator<RootStackParamList>()
const Tab      = createBottomTabNavigator<MainTabParamList>()
const MoreStack = createNativeStackNavigator<MoreStackParamList>()

// ── Tab icon ─────────────────────────────────────────────────────────────────

function TabIcon({ label, focused }: { label: string; focused: boolean }) {
  const icons: Record<string, string> = {
    Dashboard: '◈', Agents: '◉', Chat: '▷', Security: '⬡', More: '≡',
  }
  const color = focused ? Colors.gold : Colors.textDim
  return (
    <View style={styles.tabIcon}>
      <Text style={[styles.tabSymbol, { color }]}>{icons[label] ?? '·'}</Text>
    </View>
  )
}

// ── More menu screen ──────────────────────────────────────────────────────────

type MoreMenuNav = import('@react-navigation/native-stack').NativeStackNavigationProp<MoreStackParamList, 'MoreMenu'>

const moreItems: { label: string; sub: string; symbol: string; screen: keyof MoreStackParamList }[] = [
  { label: 'TASKS',    sub: 'Run & monitor agent tasks',     symbol: '▦', screen: 'Tasks' },
  { label: 'BILLING',  sub: 'Spend limits & Stripe portal',  symbol: '◎', screen: 'Billing' },
  { label: 'SETTINGS', sub: 'Account, sessions & API keys',  symbol: '⚙', screen: 'Settings' },
]

function MoreMenuScreen({ navigation }: { navigation: MoreMenuNav }) {
  return (
    <View style={styles.menuPage}>
      <View style={styles.topBar}>
        <Text style={styles.topTitle}>MORE</Text>
      </View>
      <View style={styles.menuList}>
        {moreItems.map(item => (
          <TouchableOpacity
            key={item.screen}
            style={styles.menuItem}
            onPress={() => navigation.navigate(item.screen)}
            activeOpacity={0.7}
          >
            <Text style={styles.menuSymbol}>{item.symbol}</Text>
            <View style={styles.menuText}>
              <Text style={styles.menuLabel}>{item.label}</Text>
              <Text style={styles.menuSub}>{item.sub}</Text>
            </View>
            <Text style={styles.menuChevron}>›</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  )
}

// ── More stack ────────────────────────────────────────────────────────────────

function MoreNavigator() {
  return (
    <MoreStack.Navigator screenOptions={{ headerShown: false, animation: 'slide_from_right' }}>
      <MoreStack.Screen name="MoreMenu"  component={MoreMenuScreen} />
      <MoreStack.Screen name="Tasks"     component={TasksScreen} />
      <MoreStack.Screen name="Billing"   component={BillingScreen} />
      <MoreStack.Screen name="Settings"  component={SettingsScreen} />
    </MoreStack.Navigator>
  )
}

// ── Main tab navigator ────────────────────────────────────────────────────────

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle:  styles.tabBar,
        tabBarLabel:  ({ focused }) => (
          <Text style={[styles.tabLabel, { color: focused ? Colors.gold : Colors.textDim }]}>
            {route.name.toUpperCase()}
          </Text>
        ),
        tabBarIcon:   ({ focused }) => <TabIcon label={route.name} focused={focused} />,
      })}
    >
      <Tab.Screen name="Dashboard" component={DashboardScreen} />
      <Tab.Screen name="Agents"    component={AgentsScreen} />
      <Tab.Screen name="Chat"      component={ChatScreen} />
      <Tab.Screen name="Security"  component={SecurityScreen} />
      <Tab.Screen name="More"      component={MoreNavigator} />
    </Tab.Navigator>
  )
}

// ── Root navigator ────────────────────────────────────────────────────────────

interface Props {
  serverReady: boolean
  authed:      boolean
  onSetupDone: () => void
}

export default function AppNavigator({ serverReady, authed, onSetupDone }: Props) {
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false, animation: 'fade' }}>
        {!serverReady ? (
          <Stack.Screen name="Setup">
            {() => <SetupScreen onSetupComplete={onSetupDone} />}
          </Stack.Screen>
        ) : !authed ? (
          <Stack.Screen name="Login" component={LoginScreen} />
        ) : (
          <Stack.Screen name="Main" component={MainTabs} />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  )
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: Colors.bgDeep,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    height: 60,
    paddingBottom: 6,
  },
  tabIcon:   { alignItems: 'center', justifyContent: 'center' },
  tabSymbol: { fontSize: 18 },
  tabLabel:  { fontFamily: Fonts.mono, fontSize: 7, letterSpacing: 1, marginTop: 2 },

  // More menu
  menuPage: { flex: 1, backgroundColor: Colors.bg },
  topBar: {
    paddingHorizontal: 16, paddingTop: 12, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgDeep,
  },
  topTitle:  { fontFamily: Fonts.mono, fontSize: 12, color: Colors.gold, letterSpacing: 3 },
  menuList:  { padding: 12, gap: 8 },
  menuItem: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surface1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, padding: 16,
  },
  menuSymbol:  { fontSize: 22, color: Colors.gold, marginRight: 14, width: 28, textAlign: 'center' },
  menuText:    { flex: 1 },
  menuLabel:   { fontFamily: Fonts.mono, fontSize: 11, color: Colors.text, letterSpacing: 1 },
  menuSub:     { fontFamily: Fonts.mono, fontSize: 8,  color: Colors.textDim, marginTop: 3 },
  menuChevron: { fontSize: 20, color: Colors.textDim, marginLeft: 8 },
})
