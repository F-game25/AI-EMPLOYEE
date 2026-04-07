import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { useWebSocket } from '../../hooks/useWebSocket'

export default function ChatPanel() {
  const messages = useAppStore(s => s.chatMessages)
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const addChatMessage = useAppStore(s => s.addChatMessage)
  const { sendMessage } = useWebSocket()

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    const text = input.trim()
    if (!text) return
    addChatMessage({ role: 'user', content: text, ts: Date.now() })
    sendMessage(text)
    setInput('')
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center px-4 py-2 flex-shrink-0"
        style={{ borderBottom: '1px solid rgba(245,196,0,0.1)' }}
      >
        <span className="font-mono text-xs tracking-widest" style={{ color: '#F5C400' }}>
          ORCHESTRATOR CHAT
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center mt-8">
            <p className="font-mono text-xs" style={{ color: '#333' }}>
              Send a message to the orchestrator...
            </p>
          </div>
        )}
        <AnimatePresence initial={false}>
          {messages.map((msg, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className="max-w-xs lg:max-w-md px-3 py-2 font-mono text-xs leading-relaxed"
                style={msg.role === 'user' ? {
                  background: 'rgba(245,196,0,0.1)',
                  border: '1px solid rgba(245,196,0,0.3)',
                  borderRadius: '6px 6px 2px 6px',
                  color: '#F5C400',
                  boxShadow: '0 0 10px rgba(245,196,0,0.1)',
                } : {
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '6px 6px 6px 2px',
                  color: '#ccc',
                }}
              >
                {msg.role === 'ai' && (
                  <div className="text-xs mb-1" style={{ color: '#444' }}>ORCHESTRATOR</div>
                )}
                {msg.content}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div
        className="flex items-center px-3 py-2 flex-shrink-0 gap-2"
        style={{ borderTop: '1px solid rgba(245,196,0,0.1)' }}
      >
        <span className="font-mono text-sm" style={{ color: '#F5C400' }}>{'>'}</span>
        <div className="flex-1 relative">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Enter command..."
            className="w-full font-mono text-xs outline-none bg-transparent"
            style={{ color: '#e8e8e8', caretColor: '#F5C400' }}
          />
        </div>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={handleSend}
          className="font-mono text-xs px-3 py-1"
          style={{
            border: '1px solid rgba(245,196,0,0.3)',
            color: '#F5C400',
            background: 'rgba(245,196,0,0.05)',
            borderRadius: '3px',
            cursor: 'pointer',
          }}
        >
          SEND
        </motion.button>
      </div>
    </div>
  )
}
