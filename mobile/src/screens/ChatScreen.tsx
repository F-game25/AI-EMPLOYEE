import React, { useState, useRef, useEffect } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator,
} from 'react-native'
import * as Haptics from 'expo-haptics'
import { api, ws } from '../api/secureClient'
import { useAuthStore } from '../store/authStore'
import { Colors } from '../theme/colors'
import { Fonts } from '../theme/typography'

interface Message {
  id:      string
  role:    'user' | 'assistant' | 'system'
  content: string
  ts:      number
  agent?:  string
}

function Bubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'
  const isSystem = msg.role === 'system'
  return (
    <View style={[styles.bubble, isUser && styles.bubbleUser, isSystem && styles.bubbleSystem]}>
      {msg.agent && !isUser && (
        <Text style={styles.agentLabel}>{msg.agent.toUpperCase()}</Text>
      )}
      <Text style={[styles.bubbleText, isUser && styles.bubbleTextUser, isSystem && styles.bubbleTextSystem]}>
        {msg.content}
      </Text>
      <Text style={styles.bubbleTs}>{new Date(msg.ts).toLocaleTimeString()}</Text>
    </View>
  )
}

export default function ChatScreen() {
  const { user } = useAuthStore()
  const [messages, setMessages] = useState<Message[]>([{
    id: 'welcome',
    role: 'system',
    content: 'NEXUS OS — Type a task or ask a question. The AI will route it to the best agent.',
    ts: Date.now(),
  }])
  const [input, setInput]       = useState('')
  const [sending, setSending]   = useState(false)
  const listRef = useRef<FlatList>(null)

  useEffect(() => {
    const unsubTask = ws.on('task:response', (_, data) => {
      const d = data as { content?: string; agent?: string }
      if (!d.content) return
      addMessage({ role: 'assistant', content: d.content, agent: d.agent })
    })
    const unsubNotif = ws.on('notification', (_, data) => {
      const d = data as { message?: string }
      if (!d.message) return
      addMessage({ role: 'system', content: d.message })
    })
    return () => { unsubTask(); unsubNotif() }
  }, [])

  const addMessage = (partial: Omit<Message, 'id' | 'ts'>) => {
    setMessages(prev => [...prev, { ...partial, id: `${Date.now()}-${Math.random()}`, ts: Date.now() }])
    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 80)
  }

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setSending(true)
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
    addMessage({ role: 'user', content: text })
    try {
      const res = await api.post('/api/chat', { message: text, source: 'mobile' }) as {
        response?: string; agent?: string; task_id?: string
      }
      if (res.response) {
        addMessage({ role: 'assistant', content: res.response, agent: res.agent })
      } else if (res.task_id) {
        addMessage({ role: 'system', content: `Task queued (${res.task_id}) — watching for response…` })
      }
    } catch (e: unknown) {
      addMessage({ role: 'system', content: `Error: ${(e as { message?: string }).message || 'Failed to send'}` })
    }
    setSending(false)
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={styles.page}
      keyboardVerticalOffset={60}
    >
      {/* Top bar */}
      <View style={styles.topBar}>
        <Text style={styles.topTitle}>NEXUS CHAT</Text>
        <Text style={styles.topSub}>{user?.email || ''}</Text>
      </View>

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={m => m.id}
        renderItem={({ item }) => <Bubble msg={item} />}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
      />

      {/* Input row */}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Ask or issue a task…"
          placeholderTextColor={Colors.textDim}
          multiline
          maxLength={2000}
          returnKeyType="send"
          blurOnSubmit
          onSubmitEditing={send}
        />
        <TouchableOpacity
          style={[styles.sendBtn, (!input.trim() || sending) && styles.sendBtnDisabled]}
          onPress={send}
          disabled={!input.trim() || sending}
          activeOpacity={0.8}
        >
          {sending
            ? <ActivityIndicator color={Colors.bg} size="small" />
            : <Text style={styles.sendBtnText}>▶</Text>
          }
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
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
  topSub:   { fontFamily: Fonts.mono, fontSize: 9, color: Colors.textDim, marginTop: 2 },

  list: { padding: 12, paddingBottom: 8, gap: 8 },

  bubble: {
    maxWidth: '85%', backgroundColor: Colors.surface1,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: 10, padding: 10, alignSelf: 'flex-start',
  },
  bubbleUser: {
    alignSelf: 'flex-end', backgroundColor: `${Colors.gold}18`,
    borderColor: `${Colors.gold}40`,
  },
  bubbleSystem: {
    alignSelf: 'center', maxWidth: '95%',
    backgroundColor: `${Colors.cyan}0e`, borderColor: `${Colors.cyan}30`,
  },
  agentLabel: {
    fontFamily: Fonts.mono, fontSize: 7, color: Colors.gold,
    letterSpacing: 1.5, marginBottom: 4,
  },
  bubbleText:       { fontFamily: Fonts.mono, fontSize: 11, color: Colors.textMuted, lineHeight: 17 },
  bubbleTextUser:   { color: Colors.text },
  bubbleTextSystem: { fontFamily: Fonts.mono, fontSize: 9, color: Colors.cyan, textAlign: 'center' },
  bubbleTs: { fontFamily: Fonts.mono, fontSize: 7, color: Colors.textDim, marginTop: 6, textAlign: 'right' },

  inputRow: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 8,
    padding: 10, borderTopWidth: 1, borderTopColor: Colors.border,
    backgroundColor: Colors.bgDeep,
  },
  input: {
    flex: 1, backgroundColor: Colors.surface1,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: 8, padding: 10,
    color: Colors.text, fontFamily: Fonts.mono, fontSize: 12,
    maxHeight: 100,
  },
  sendBtn: {
    backgroundColor: Colors.gold,
    borderRadius: 8, width: 42, height: 42,
    alignItems: 'center', justifyContent: 'center',
  },
  sendBtnDisabled: { opacity: 0.4 },
  sendBtnText:     { fontSize: 16, color: Colors.bg, fontWeight: '700' },
})
