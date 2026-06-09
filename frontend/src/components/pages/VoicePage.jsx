import { useState, useEffect } from 'react'
import { Panel, Badge, StatCard, DataRow } from '../ui/primitives'
import api from '../../api/client'

const TONES = ['warm_confident','calm','focused','curious','concerned','firm','urgent','subtle_excited']

const PRESETS = [
  { name:'Executive',     gender:'male',    tone:'firm',           pitch:0.9, speed:0.95, articulation:0.85, friendliness:0.45 },
  { name:'Warm Advisor',  gender:'female',  tone:'warm_confident', pitch:1.1, speed:1.0, articulation:0.65, friendliness:0.65 },
  { name:'Calm Guide',    gender:'neutral', tone:'calm',          pitch:1.0, speed:0.9, articulation:0.7,  friendliness:0.7 },
  { name:'Energetic',     gender:'female',  tone:'subtle_excited', pitch:1.2, speed:1.08, articulation:0.75, friendliness:0.6 },
  { name:'Analyst',       gender:'male',    tone:'focused',        pitch:1.0, speed:1.05, articulation:0.9,  friendliness:0.45 },
  { name:'Concerned',     gender:'neutral', tone:'concerned',      pitch:1.0, speed:0.92, articulation:0.75, friendliness:0.55 },
]

const BARS = [12,18,28,42,55,38,62,71,58,44,32,25,38,48,60,72,65,50,38,28,18,12,8,14]

function Slider({ label, value, min, max, step = 0.01, color, onChange, format }) {
  return (
    <div style={{ marginBottom:8 }}>
      <div style={{ display:'flex', justifyContent:'space-between', fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', marginBottom:4 }}>
        <span>{label}</span><span style={{ color }}>{format ? format(value) : value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        style={{ width:'100%', accentColor: color || 'var(--gold,#E5C76B)' }}/>
    </div>
  )
}

function MiniBar({ value, color }) {
  return (
    <div style={{ height:3, background:'rgba(255,255,255,0.06)', borderRadius:2 }}>
      <div style={{ width:`${value * 100}%`, height:'100%', background: color || 'var(--gold,#E5C76B)', boxShadow:`0 0 6px ${color || 'var(--gold,#E5C76B)'}`, borderRadius:2 }}/>
    </div>
  )
}

export default function VoicePage() {
  const [tab, setTab] = useState('studio')
  const [testText, setTestText] = useState('Hello, I am your AI Employee. How can I assist you today?')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [backendStatus, setBackendStatus] = useState(null)
  const [active, setActive] = useState(false)

  // Persona params
  const [gender, setGender] = useState('neutral')
  const [tone, setTone] = useState('warm_confident')
  const [pitch, setPitch] = useState(1.0)
  const [speed, setSpeed] = useState(1.0)
  const [articulation, setArticulation] = useState(0.7)
  const [friendliness, setFriendliness] = useState(0.6)

  const persona = { provider: 'voice_core_local', gender, tone, emotion: tone, emotion_intensity: friendliness * 0.7, speaking_rate: speed, pitch, articulation, friendliness }

  useEffect(() => {
    api.voice.runtime().then(setBackendStatus).catch(() => setBackendStatus({ ok: false }))
  }, [])

  const applyPreset = (p) => {
    setGender(p.gender); setTone(p.tone)
    setPitch(p.pitch);   setSpeed(p.speed)
    setArticulation(p.articulation); setFriendliness(p.friendliness)
  }

  const handleTest = async () => {
    if (!testText.trim()) return
    setTesting(true); setTestResult(null)
    try {
      const token = sessionStorage.getItem('ai_jwt')
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const res = await fetch('/api/voice/synthesize', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          text: testText.trim(),
          provider: 'voice_core_local',
          voice: 'default',
          emotion: tone,
          emotion_intensity: friendliness * 0.7,
          speaking_rate: speed,
          persona,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.error || body.setup || `HTTP ${res.status}`)
      }
      const audio = new Audio(URL.createObjectURL(await res.blob()))
      await audio.play()
      setTestResult({ ok: true, message: `Synthesized with ${res.headers.get('X-Voice-Provider') || 'default voice'}`, chars: testText.length })
    } catch (e) {
      setTestResult({ ok: false, message: e.message || 'Synthesis failed' })
    } finally {
      setTesting(false)
    }
  }

  const tabBtn = (id, label) => (
    <button onClick={() => setTab(id)} style={{
      padding:'5px 14px', borderRadius:6, fontSize:10, fontFamily:'monospace', letterSpacing:'0.06em',
      background: tab === id ? 'rgba(229,199,107,0.15)' : 'transparent',
      border: tab === id ? '1px solid rgba(229,199,107,0.4)' : '1px solid rgba(255,255,255,0.08)',
      color: tab === id ? 'var(--gold,#E5C76B)' : 'rgba(255,255,255,0.4)', cursor:'pointer',
    }}>{label}</button>
  )

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10, height:'100%' }}>
      {/* Stats row */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10 }}>
        <StatCard label="Backend"    value={backendStatus?.ok ? 'ONLINE' : 'OFFLINE'} color={backendStatus?.ok ? '#22C55E' : '#ef4444'} sub="Local voice runtime"/>
        <StatCard label="Model"      value={backendStatus?.tts?.voice_core_local?.state || 'unknown'} color="var(--gold,#E5C76B)" sub="Default Human Voice"/>
        <StatCard label="Emotions"   value={`${TONES.length}`} color="var(--teal,#20D6C7)" sub="Subtle styles"/>
      </div>

      {/* Tab bar */}
      <div style={{ display:'flex', gap:8 }}>
        {tabBtn('studio', 'PERSONA STUDIO')}
        {tabBtn('presets', 'PRESETS')}
      </div>

      {tab === 'studio' && (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, flex:1, minHeight:0 }}>
          {/* Left: controls */}
          <Panel title="Persona Configuration" bodyStyle={{ overflowY:'auto' }}>
            {/* Gender */}
            <div style={{ marginBottom:12 }}>
              <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', marginBottom:6 }}>GENDER</div>
              <div style={{ display:'flex', gap:6 }}>
                {['male','female','neutral'].map(g => (
                  <button key={g} onClick={() => setGender(g)} style={{
                    flex:1, padding:'5px 0', borderRadius:5, fontSize:10, fontFamily:'monospace', textTransform:'uppercase',
                    background: gender === g ? 'rgba(229,199,107,0.15)' : 'transparent',
                    border: gender === g ? '1px solid rgba(229,199,107,0.5)' : '1px solid rgba(255,255,255,0.1)',
                    color: gender === g ? 'var(--gold,#E5C76B)' : 'rgba(255,255,255,0.4)', cursor:'pointer',
                  }}>{g}</button>
                ))}
              </div>
            </div>

            {/* Tone */}
            <div style={{ marginBottom:12 }}>
              <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.35)', marginBottom:6 }}>EMOTION STYLE</div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:4 }}>
                {TONES.map(t => (
                  <button key={t} onClick={() => setTone(t)} style={{
                    padding:'4px 0', borderRadius:4, fontSize:9, fontFamily:'monospace', textTransform:'uppercase',
                    background: tone === t ? 'rgba(32,214,199,0.15)' : 'transparent',
                    border: tone === t ? '1px solid rgba(32,214,199,0.4)' : '1px solid rgba(255,255,255,0.08)',
                    color: tone === t ? 'var(--teal,#20D6C7)' : 'rgba(255,255,255,0.35)', cursor:'pointer',
                  }}>{t}</button>
                ))}
              </div>
            </div>

            <Slider label="PITCH" value={pitch} min={0.5} max={2.0} step={0.05} color="var(--gold,#E5C76B)" onChange={setPitch} format={v => `${v.toFixed(2)}×`}/>
            <Slider label="SPEED" value={speed} min={0.5} max={2.0} step={0.05} color="var(--teal,#20D6C7)" onChange={setSpeed} format={v => `${v.toFixed(2)}×`}/>
            <Slider label="ARTICULATION" value={articulation} min={0} max={1} step={0.05} color="#a855f7" onChange={setArticulation} format={v => `${Math.round(v*100)}%`}/>
            <Slider label="FRIENDLINESS" value={friendliness} min={0} max={1} step={0.05} color="#f97316" onChange={setFriendliness} format={v => `${Math.round(v*100)}%`}/>

            {/* Current persona summary */}
            <div style={{ marginTop:8, padding:'8px 10px', borderRadius:6, background:'rgba(229,199,107,0.04)', border:'1px solid rgba(229,199,107,0.12)', fontSize:10, fontFamily:'monospace' }}>
              <div style={{ color:'rgba(255,255,255,0.35)', marginBottom:4 }}>CURRENT PERSONA</div>
              {Object.entries(persona).map(([k,v]) => (
                <div key={k} style={{ display:'flex', justifyContent:'space-between', marginBottom:2 }}>
                  <span style={{ color:'rgba(255,255,255,0.4)' }}>{k}</span>
                  <span style={{ color:'var(--gold,#E5C76B)' }}>{typeof v === 'number' && k !== 'pitch' && k !== 'speed' ? v.toFixed(2) : String(v)}</span>
                </div>
              ))}
            </div>
          </Panel>

          {/* Right: test panel */}
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            <Panel title="Test Default Human Voice" badge={<Badge label={backendStatus?.tts?.voice_core_local?.state === 'ready' ? 'READY' : 'NOT READY'} variant={backendStatus?.tts?.voice_core_local?.state === 'ready' ? 'teal' : 'default'}/>}>
              {/* Waveform visualizer */}
              <div onClick={() => setActive(a => !a)} style={{ display:'flex', alignItems:'flex-end', justifyContent:'center', gap:2, height:48, marginBottom:12, cursor:'pointer' }}>
                {BARS.map((h, i) => (
                  <div key={i} style={{ width:5, height:`${active ? h : h * 0.2}%`, background: active ? 'var(--teal,#20D6C7)' : 'rgba(255,255,255,0.12)', borderRadius:2, transition:`height ${0.1 + i * 0.01}s ease` }}/>
                ))}
              </div>

              <textarea
                value={testText}
                onChange={e => setTestText(e.target.value)}
                rows={4}
                placeholder="Enter text to synthesize..."
                style={{ width:'100%', resize:'vertical', padding:'8px 10px', borderRadius:6, background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.1)', color:'var(--text-primary,#F0E9D2)', fontFamily:'monospace', fontSize:12, boxSizing:'border-box' }}
              />

              <button onClick={handleTest} disabled={testing || !testText.trim()} style={{
                width:'100%', marginTop:8, padding:'8px 0', borderRadius:6, fontSize:11, fontFamily:'monospace', fontWeight:600,
                background: testing ? 'rgba(229,199,107,0.05)' : 'rgba(229,199,107,0.15)',
                border:'1px solid rgba(229,199,107,0.4)', color:'var(--gold,#E5C76B)', cursor: testing ? 'wait' : 'pointer',
              }}>
                {testing ? 'SYNTHESIZING...' : 'TEST VOICE'}
              </button>

              {testResult && (
                <div style={{ marginTop:8, padding:'8px 10px', borderRadius:6, background: testResult.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)', border:`1px solid ${testResult.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`, fontSize:11, fontFamily:'monospace', color: testResult.ok ? '#22C55E' : '#ef4444' }}>
                  {testResult.ok ? '✓ ' : '✗ '}{testResult.message}
                </div>
              )}
            </Panel>

            <Panel title="Local Voice Status" style={{ flex:1 }}>
              {backendStatus ? (
                <>
                  <DataRow label="Default voice" value={backendStatus.tts?.voice_core_local?.state || 'unknown'} color={backendStatus.tts?.voice_core_local?.state === 'ready' ? '#22C55E' : '#ef4444'}/>
                  <DataRow label="EN voice"     value={backendStatus.tts?.voice_core_local?.tts_en_ready ? backendStatus.tts?.voice_core_local?.active_voice?.voice || 'af_heart' : 'missing'}/>
                  <DataRow label="NL voice"     value={backendStatus.tts?.voice_core_local?.tts_nl_ready ? 'nl_NL-mls-medium' : 'missing'}/>
                  <DataRow label="No install"   value={backendStatus.tts?.voice_core_local?.requires_installation === false ? 'YES' : 'NO'}/>
                  {backendStatus.tts?.voice_core_local?.state !== 'ready' && (
                    <div style={{ marginTop:8, fontSize:10, fontFamily:'monospace', color:'rgba(239,68,68,0.7)', padding:'6px 8px', background:'rgba(239,68,68,0.06)', borderRadius:5, border:'1px solid rgba(239,68,68,0.2)' }}>
                      {backendStatus.tts?.voice_core_local?.recommendation || 'Packaged Default Human Voice bundle is not ready.'}
                    </div>
                  )}
                </>
              ) : (
                <div style={{ color:'rgba(255,255,255,0.3)', fontSize:11, fontFamily:'monospace' }}>Checking backend...</div>
              )}
            </Panel>
          </div>
        </div>
      )}

      {tab === 'presets' && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, flex:1, minHeight:0, alignContent:'start' }}>
          {PRESETS.map((p) => (
            <div key={p.name} style={{ padding:14, borderRadius:10, background:'rgba(255,255,255,0.03)', border:'1px solid rgba(229,199,107,0.12)', display:'flex', flexDirection:'column', gap:8 }}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:4 }}>
                <span style={{ fontSize:13, color:'var(--text-primary,#F0E9D2)', fontWeight:600 }}>{p.name}</span>
                <Badge label={p.gender.toUpperCase()} variant="default"/>
              </div>
              <div style={{ fontSize:10, fontFamily:'monospace', color:'var(--teal,#20D6C7)', marginBottom:4 }}>{p.tone}</div>
              <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
                {[['Pitch', p.pitch / 2],['Speed', p.speed / 2],['Articulation', p.articulation],['Friendliness', p.friendliness]].map(([lbl,val]) => (
                  <div key={lbl}>
                    <div style={{ fontSize:9, fontFamily:'monospace', color:'rgba(255,255,255,0.3)', marginBottom:2 }}>{lbl}</div>
                    <MiniBar value={val} color="var(--gold,#E5C76B)"/>
                  </div>
                ))}
              </div>
              <button onClick={() => { applyPreset(p); setTab('studio') }} style={{
                marginTop:4, padding:'5px 0', borderRadius:5, fontSize:10, fontFamily:'monospace',
                background:'rgba(229,199,107,0.1)', border:'1px solid rgba(229,199,107,0.35)',
                color:'var(--gold,#E5C76B)', cursor:'pointer', width:'100%',
              }}>SELECT PRESET</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
