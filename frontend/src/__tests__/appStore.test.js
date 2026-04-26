import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from '../store/appStore'

beforeEach(() => {
  useAppStore.setState({
    activeSection: 'dashboard',
    sidebarCollapsed: false,
    appState: 'boot',
    hermesGoal: '',
    automationRules: [],
    alphaArchive: [],
  })
})

describe('appStore', () => {
  it('setActiveSection updates activeSection', () => {
    useAppStore.getState().setActiveSection('agents')
    expect(useAppStore.getState().activeSection).toBe('agents')
  })

  it('setSidebarCollapsed toggles sidebar', () => {
    useAppStore.getState().setSidebarCollapsed(true)
    expect(useAppStore.getState().sidebarCollapsed).toBe(true)
    useAppStore.getState().setSidebarCollapsed(false)
    expect(useAppStore.getState().sidebarCollapsed).toBe(false)
  })

  it('addAutomationRule appends and removeAutomationRule deletes', () => {
    const rule = { id: 'r1', trigger: 'Agent Failed', action: 'Restart Agent' }
    useAppStore.getState().addAutomationRule(rule)
    expect(useAppStore.getState().automationRules).toHaveLength(1)
    useAppStore.getState().removeAutomationRule('r1')
    expect(useAppStore.getState().automationRules).toHaveLength(0)
  })

  it('addAlphaEntry limits archive to 100 entries', () => {
    for (let i = 0; i < 105; i++) {
      useAppStore.getState().addAlphaEntry({ id: i, name: `entry-${i}` })
    }
    expect(useAppStore.getState().alphaArchive).toHaveLength(100)
  })

  it('login transitions appState to dashboard', () => {
    useAppStore.getState().login('operator')
    expect(useAppStore.getState().appState).toBe('dashboard')
  })
})
