/**
 * NexusOS Dashboard — Phase 1
 * Layout: exact match to reference image
 * Top KPI strip → Neural Core (center) + right column → bottom 3-panel row
 */

import React, { useCallback, useEffect, useRef, useState, memo, useMemo, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Text } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import { motion, AnimatePresence } from 'framer-motion';
import * as THREE from 'three';
import { useAppStore } from '../../store/appStore';
import './NexusOSDashboard.css';

// ─── theme tokens ────────────────────────────────────────────────────────────
const T = {
  bg:        '#07080f',
  bgCard:    '#0c0e1a',
  bgPanel:   'rgba(12,14,26,0.92)',
  border:    'rgba(229,199,107,0.18)',
  borderHi:  'rgba(229,199,107,0.45)',
  gold:      '#e5c76b',
  goldDim:   '#c9a94a',
  goldGlow:  'rgba(229,199,107,0.15)',
  purple:    '#a855f7',
  crimson:   '#ef4444',
  cyan:      '#06b6d4',
  silver:    '#94a3b8',
  text:      '#f0e9d6',
  textDim:   '#8b7e5a',
  textMuted: '#4a4035',
  green:     '#22c55e',
};

// ─── KPI strip data ───────────────────────────────────────────────────────────
const KPI_TILES = [
  { id: 'revenue',    label: 'TOTAL REVENUE',        icon: '◈', color: T.gold,    format: v => `$${(v/1e6).toFixed(2)}M` },
  { id: 'agents',     label: 'ACTIVE AGENTS',        icon: '⬡', color: T.cyan,    format: v => String(v) },
  { id: 'tokens',     label: 'LLM TOKENS / SEC',     icon: '⬟', color: T.gold,    format: v => `${(v/1e6).toFixed(2)}M` },
  { id: 'uptime',     label: 'SYSTEM UPTIME',        icon: '◎', color: T.green,   format: v => `${v.toFixed(3)}%` },
  { id: 'tasks',      label: 'TASKS COMPLETED',      icon: '▸', color: T.gold,    format: v => String(v) },
  { id: 'security',   label: 'SECURITY SCORE',       icon: '⬡', color: T.gold,    format: v => `${v.toFixed(1)} / 100` },
];

// ─── orbital subsystem node configs (8 nodes like reference) ─────────────────
const NODE_CONFIGS = [
  { id: 'orchestrator', label: 'MASTER ORCHESTRATOR', pct: '100%', tps: '2,476 t/s', angle: Math.PI/2,           radius: 2.2, color: [1.0, 0.85, 0.48], size: 0.28 },
  { id: 'memory',       label: 'MEMORY UNIVERSE',      pct: '98%',  tps: '1,982 t/s', angle: Math.PI*2/5 + Math.PI/2, radius: 2.6, color: [0.67,0.33,0.97],  size: 0.22 },
  { id: 'vector',       label: 'VECTOR DATABASE',       pct: '98%',  tps: '1,756 t/s', angle: -Math.PI/5 + Math.PI/2,  radius: 2.6, color: [0.24,0.83,1.0],   size: 0.22 },
  { id: 'models',       label: 'MODEL CLUSTER',         pct: '96%',  tps: '3,421 t/s', angle: Math.PI + Math.PI*2/5,   radius: 2.4, color: [0.8,0.5,0.2],     size: 0.22 },
  { id: 'tools',        label: 'TOOL LAYER',            pct: '97%',  tps: '2,193 t/s', angle: -Math.PI/5,               radius: 2.4, color: [0.8,0.75,0.9],    size: 0.22 },
  { id: 'security',     label: 'SECURITY GRID',         pct: '99%',  tps: '1,102 t/s', angle: Math.PI + Math.PI/5,      radius: 2.4, color: [0.8,0.15,0.15],   size: 0.20 },
  { id: 'execution',    label: 'EXECUTION ENGINE',      pct: '99%',  tps: '4,213 t/s', angle: -Math.PI/2,               radius: 2.2, color: [0.48,0.85,1.0],   size: 0.24 },
  { id: 'agents',       label: 'AGENT SWARM',           pct: '99%',  tps: '958 t/s',   angle: Math.PI,                  radius: 2.2, color: [1.0,0.85,0.48],   size: 0.22 },
];

// ─── Three.js scene ───────────────────────────────────────────────────────────
function CoreSphereGold({ load = 0.5, thinking = 0 }) {
  const meshRef = useRef();
  const matRef  = useRef();
  const t0 = useRef(Date.now());

  useFrame(() => {
    if (!meshRef.current || !matRef.current) return;
    const elapsed = (Date.now() - t0.current) * 0.001;
    meshRef.current.rotation.y += 0.003 + load * 0.004;
    meshRef.current.rotation.x += 0.001;
    matRef.current.uniforms.u_time.value = elapsed;
    matRef.current.uniforms.u_load.value  = load;
    matRef.current.uniforms.u_think.value = thinking;
  });

  const vert = `
    varying vec3 vNorm; varying vec3 vPos; uniform float u_time; uniform float u_load; uniform float u_think;
    float h(float n){return fract(sin(n)*43758.5453);}
    float ns(vec3 x){vec3 p=floor(x);vec3 f=fract(x);f=f*f*(3.-2.*f);float n=p.x+p.y*157.+113.*p.z;return mix(mix(mix(h(n),h(n+1.),f.x),mix(h(n+157.),h(n+158.),f.x),f.y),mix(mix(h(n+113.),h(n+114.),f.x),mix(h(n+270.),h(n+271.),f.x),f.y),f.z);}
    void main(){vNorm=normalize(normalMatrix*normal);vPos=position;
    float d=ns(position*2.+u_time*.5)*u_load*.12+ns(position*4.+u_time*.3)*u_think*.06;
    gl_Position=projectionMatrix*modelViewMatrix*vec4(position+normal*d,1.);}
  `;
  const frag = `
    varying vec3 vNorm; varying vec3 vPos; uniform float u_load; uniform float u_think;
    void main(){vec3 n=normalize(vNorm);vec3 v=normalize(-vPos);float fr=pow(1.-max(dot(n,v),0.),3.);
    vec3 base=mix(vec3(.05,.06,.12),vec3(.18,.13,.04),u_load);
    base=mix(base,vec3(.65,.33,.97),u_think*.25);
    vec3 rim=vec3(1.,.85,.48);vec3 c=mix(base,rim,fr*.7);
    gl_FragColor=vec4(c,0.88);}
  `;

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1, 6]} />
      <shaderMaterial ref={matRef} vertexShader={vert} fragmentShader={frag}
        uniforms={{ u_time:{value:0}, u_load:{value:0.5}, u_think:{value:0} }}
        transparent />
    </mesh>
  );
}

function SynapticLink({ from, to, color }) {
  const ref = useRef();
  const t0  = useRef(Math.random() * 6.28);

  const points = useMemo(() => {
    const mid = new THREE.Vector3().addVectors(from, to).multiplyScalar(0.5);
    mid.y += 0.3;
    const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
    return curve.getPoints(20);
  }, [from, to]);

  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.getElapsedTime();
    ref.current.material.opacity = 0.15 + Math.sin(t * 1.5 + t0.current) * 0.12;
  });

  return (
    <line ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position"
          array={new Float32Array(points.flatMap(p => [p.x, p.y, p.z]))}
          count={points.length} itemSize={3} />
      </bufferGeometry>
      <lineBasicMaterial color={new THREE.Color(...color)} transparent opacity={0.2} />
    </line>
  );
}

function OrbitalNode({ cfg, speed = 0.12 }) {
  const grp  = useRef();
  const mesh = useRef();
  const pLight = useRef();
  const t0   = useRef(cfg.angle);

  useFrame(({ clock }) => {
    if (!grp.current) return;
    const t = clock.getElapsedTime();
    const a = t0.current + t * speed * (0.8 + Math.random() * 0.001);
    grp.current.position.set(
      Math.cos(a) * cfg.radius,
      Math.sin(t * 0.3 + t0.current) * 0.15,
      Math.sin(a) * cfg.radius,
    );
    if (mesh.current) mesh.current.rotation.z += 0.015;
    if (pLight.current) {
      pLight.current.intensity = 0.6 + Math.sin(t * 2 + t0.current) * 0.2;
    }
  });

  const col = new THREE.Color(...cfg.color);

  return (
    <group ref={grp}>
      <mesh ref={mesh}>
        <octahedronGeometry args={[cfg.size, 0]} />
        <meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.8} />
      </mesh>
      <pointLight ref={pLight} intensity={0.7} distance={2.5} color={col} />
    </group>
  );
}

function ParticleRing({ count = 3000, load = 0.5 }) {
  const pts = useRef();

  const { positions, velocities } = useMemo(() => {
    const positions  = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = 1.3 + Math.random() * 1.4;
      positions[i*3]   = Math.cos(a) * r;
      positions[i*3+1] = (Math.random() - 0.5) * 1.8;
      positions[i*3+2] = Math.sin(a) * r;
      velocities[i*3]  =  Math.cos(a + Math.PI/2) * 0.5;
      velocities[i*3+1]= (Math.random()-0.5)*0.15;
      velocities[i*3+2]=  Math.sin(a + Math.PI/2) * 0.5;
    }
    return { positions, velocities };
  }, [count]);

  const colors = useMemo(() => {
    const c = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = Math.random();
      if (r < 0.8) { c[i*3]=1; c[i*3+1]=0.85; c[i*3+2]=0.48; }
      else if (r < 0.92) { c[i*3]=0.67; c[i*3+1]=0.33; c[i*3+2]=0.97; }
      else { c[i*3]=0.24; c[i*3+1]=0.83; c[i*3+2]=1; }
    }
    return c;
  }, [count]);

  useFrame(() => {
    if (!pts.current) return;
    const p = pts.current.geometry.attributes.position.array;
    const s = (0.008 + load * 0.006);
    for (let i = 0; i < count; i++) {
      p[i*3]   += velocities[i*3]   * s;
      p[i*3+2] += velocities[i*3+2] * s;
      const r = Math.sqrt(p[i*3]**2 + p[i*3+2]**2);
      if (r > 3.2) {
        const a = Math.atan2(p[i*3+2], p[i*3]);
        const nr = 1.3 + Math.random()*0.5;
        p[i*3]   = Math.cos(a) * nr;
        p[i*3+2] = Math.sin(a) * nr;
      }
    }
    pts.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pts}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={positions} count={count} itemSize={3} />
        <bufferAttribute attach="attributes-color"    array={colors}    count={count} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.035} sizeAttenuation vertexColors transparent opacity={0.75} />
    </points>
  );
}

function NeuralCoreScene({ metrics }) {
  const { load=0.5, thinking=0, taskRate=0.5 } = metrics;

  // Precompute static node world positions for synaptic links
  const nodePositions = useMemo(() =>
    NODE_CONFIGS.map(c => new THREE.Vector3(
      Math.cos(c.angle)*c.radius, 0, Math.sin(c.angle)*c.radius
    )), []);

  const origin = new THREE.Vector3(0,0,0);

  return (
    <>
      <PerspectiveCamera makeDefault position={[0,2.5,5.5]} fov={48} />
      <OrbitControls enableDamping dampingFactor={0.06} enableZoom enablePan={false}
        autoRotate={false} minDistance={3} maxDistance={10} />

      <ambientLight intensity={0.25} color="#1a1820" />
      <pointLight position={[4,4,4]} intensity={1.2} color="#e5c76b" />
      <pointLight position={[-4,-3,4]} intensity={0.6} color="#a855f7" />
      <pointLight position={[0,0,0]}  intensity={0.4} color="#e5c76b" />

      <Suspense fallback={null}>
        <CoreSphereGold load={load} thinking={thinking} />
        <ParticleRing count={2500} load={load} />

        {NODE_CONFIGS.map(cfg => <OrbitalNode key={cfg.id} cfg={cfg} />)}

        {/* Synaptic links from center to each node */}
        {NODE_CONFIGS.map((cfg, i) => (
          <SynapticLink key={cfg.id} from={origin} to={nodePositions[i]} color={cfg.color} />
        ))}
        {/* Cross links between adjacent nodes */}
        {NODE_CONFIGS.map((cfg, i) => {
          const next = NODE_CONFIGS[(i+2) % NODE_CONFIGS.length];
          return <SynapticLink key={`x${i}`} from={nodePositions[i]} to={nodePositions[NODE_CONFIGS.indexOf(next)]} color={cfg.color} />;
        })}
      </Suspense>

      <EffectComposer>
        <Bloom intensity={0.8 + load * 0.6} luminanceThreshold={0.25} luminanceSmoothing={0.9} />
      </EffectComposer>
    </>
  );
}

// ─── UI building blocks ───────────────────────────────────────────────────────
function Panel({ title, badge, children, style, className }) {
  return (
    <div className={`nexus-panel ${className||''}`} style={style}>
      {title && (
        <div className="nexus-panel-header">
          <span className="nexus-panel-title">{title}</span>
          {badge && <span className="nexus-panel-badge">{badge}</span>}
        </div>
      )}
      <div className="nexus-panel-body">{children}</div>
    </div>
  );
}

function Sparkline({ values = [], color = T.gold, height = 32 }) {
  const w = 120, h = height;
  if (!values.length) return <svg width={w} height={h} />;
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => `${(i/(values.length-1))*w},${h - (v/max)*h}`).join(' ');
  return (
    <svg width={w} height={h} style={{ overflow:'visible' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function AnimatedNumber({ value, format = v => v.toFixed(0) }) {
  const [disp, setDisp] = useState(value);
  const ref = useRef(value);
  useEffect(() => {
    const diff = value - ref.current;
    const steps = 20;
    let step = 0;
    const id = setInterval(() => {
      step++;
      setDisp(ref.current + diff * (step/steps));
      if (step >= steps) { ref.current = value; clearInterval(id); }
    }, 16);
    return () => clearInterval(id);
  }, [value]);
  return <span>{format(disp)}</span>;
}

// ─── KPI strip ────────────────────────────────────────────────────────────────
function KPIStrip({ kpis }) {
  return (
    <div className="nexus-kpi-strip">
      {KPI_TILES.map((tile, i) => {
        const val = kpis[tile.id] ?? 0;
        const delta = kpis[`${tile.id}_delta`] ?? null;
        return (
          <motion.div key={tile.id} className="nexus-kpi-tile"
            initial={{ opacity:0, y:-8 }} animate={{ opacity:1, y:0 }}
            transition={{ delay: i*0.07, duration:0.4 }}>
            <div className="kpi-icon" style={{ color: tile.color }}>{tile.icon}</div>
            <div className="kpi-body">
              <div className="kpi-value" style={{ color: tile.color }}>
                <AnimatedNumber value={val} format={tile.format} />
              </div>
              <div className="kpi-label">{tile.label}</div>
              {delta !== null && (
                <div className={`kpi-delta ${delta >= 0 ? 'up' : 'down'}`}>
                  {delta >= 0 ? '+' : ''}{delta.toFixed(1)}%
                  {i === 0 && <span className="kpi-sub"> (24h)</span>}
                </div>
              )}
            </div>
          </motion.div>
        );
      })}
      <div className="nexus-kpi-nav">›</div>
    </div>
  );
}

// ─── Right column panels ──────────────────────────────────────────────────────
const COGNITION_STEPS = [
  'Analyzing user request',
  'Retrieving relevant memories',
  'Selecting optimal model',
  'Delegating to agent swarm',
  'Executing task pipeline',
  'Verifying results',
];

function CognitionStream({ thinking }) {
  const [steps, setSteps] = useState([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    if (!thinking) { setSteps([]); setTotal(0); return; }
    let i = 0;
    const id = setInterval(() => {
      if (i < COGNITION_STEPS.length) {
        const t = 1.2 + Math.random() * 2.1;
        setSteps(s => [...s, { label: COGNITION_STEPS[i], t }]);
        setTotal(prev => prev + t);
        i++;
      } else clearInterval(id);
    }, 500);
    return () => clearInterval(id);
  }, [thinking]);

  return (
    <Panel title="LIVE COGNITION STREAM" style={{ height:'100%' }}>
      <div className="cognition-brain-icon">
        <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
          <circle cx="32" cy="32" r="28" stroke={T.gold} strokeWidth="1" opacity="0.3" />
          <circle cx="32" cy="32" r="18" stroke={T.gold} strokeWidth="0.5" opacity="0.2" />
          {[...Array(8)].map((_,i) => (
            <line key={i}
              x1="32" y1="32"
              x2={32 + Math.cos(i*Math.PI/4)*26}
              y2={32 + Math.sin(i*Math.PI/4)*26}
              stroke={T.gold} strokeWidth="0.5" opacity="0.2"
            />
          ))}
          <circle cx="32" cy="32" r="5" fill={T.gold} opacity="0.6" />
        </svg>
      </div>
      {steps.length === 0 && (
        <div style={{ color: T.textDim, fontSize:11, textAlign:'center', paddingTop:8 }}>
          Waiting for task...
        </div>
      )}
      <AnimatePresence>
        {steps.map((s, i) => (
          <motion.div key={i} className="cognition-step"
            initial={{ opacity:0, x:-8 }} animate={{ opacity:1, x:0 }}
            transition={{ duration:0.3 }}>
            <span className="cog-dot">◉</span>
            <span className="cog-label">{s.label}</span>
            <span className="cog-time">{s.t.toFixed(1)}s</span>
          </motion.div>
        ))}
      </AnimatePresence>
      {steps.length > 0 && (
        <div className="cognition-total">
          TOTAL TIME <span style={{ color: T.gold }}>{total.toFixed(1)}s</span>
        </div>
      )}
    </Panel>
  );
}

function AgentSwarmHeatmap({ agents = [] }) {
  const hexes = useMemo(() => Array.from({ length: 48 }, (_, i) => {
    const agent = agents[i];
    const status = agent?.status || (Math.random() > 0.15 ? 'active' : Math.random() > 0.5 ? 'busy' : 'idle');
    return { id: i, status };
  }), [agents]);

  const counts = useMemo(() => ({
    total: 128,
    active: agents.filter(a => a?.status === 'active').length || 102,
    busy: agents.filter(a => a?.status === 'busy').length || 18,
    idle: agents.filter(a => a?.status === 'idle').length || 8,
    failed: agents.filter(a => a?.status === 'failed').length || 0,
  }), [agents]);

  const colorMap = { active: T.green, busy: T.gold, idle: T.textMuted, failed: T.crimson };

  return (
    <Panel title="AGENT SWARM OVERVIEW" badge="LIVE" style={{ flex:'0 0 auto' }}>
      <div className="swarm-hex-grid">
        {hexes.map(h => (
          <div key={h.id} className="swarm-hex" style={{ background: colorMap[h.status] }} />
        ))}
      </div>
      <div className="swarm-legend">
        {[['TOTAL AGENTS', counts.total, T.text],
          ['ACTIVE', counts.active, T.green],
          ['BUSY', counts.busy, T.gold],
          ['IDLE', counts.idle, T.silver],
          ['FAILED', counts.failed, T.crimson]].map(([k,v,c]) => (
          <div key={k} className="swarm-stat">
            <span style={{ color: T.textDim, fontSize:9 }}>{k}</span>
            <span style={{ color: c, fontSize:13, fontWeight:700 }}>{v}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function TelemetryPanel({ metrics }) {
  const histories = useRef({ cpu:[], gpu:[], ram:[], vram:[] });

  useEffect(() => {
    const h = histories.current;
    h.cpu  = [...h.cpu.slice(-30),  metrics.cpu  ?? 28];
    h.gpu  = [...h.gpu.slice(-30),  metrics.gpu  ?? 42];
    h.ram  = [...h.ram.slice(-30),  metrics.ram  ?? 71];
    h.vram = [...h.vram.slice(-30), metrics.vram ?? 63];
  }, [metrics]);

  const rows = [
    ['CPU',  metrics.cpu  ?? 28, T.cyan,   histories.current.cpu],
    ['GPU',  metrics.gpu  ?? 42, T.purple, histories.current.gpu],
    ['RAM',  metrics.ram  ?? 71, T.gold,   histories.current.ram],
    ['VRAM', metrics.vram ?? 63, T.silver, histories.current.vram],
  ];

  return (
    <Panel title="SYSTEM TELEMETRY" badge="REAL-TIME" style={{ flex:'0 0 auto' }}>
      <div className="telemetry-grid">
        {rows.map(([label, val, color, hist]) => (
          <div key={label} className="telemetry-item">
            <div className="tel-top">
              <span className="tel-label">{label}</span>
              <span className="tel-val" style={{ color }}>{Math.round(val)}%</span>
            </div>
            <Sparkline values={hist} color={color} height={28} />
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ─── Bottom row panels ────────────────────────────────────────────────────────
function RevenuePanel({ metrics }) {
  const data = [
    ['AI Services', '48%', T.gold],
    ['Automation',  '28%', T.cyan],
    ['Consulting',  '15%', T.purple],
    ['SaaS',        '9%',  T.silver],
  ];

  const campaigns = [
    { name: 'AI Lead Gen v3',     rev: '$8.2M',  delta: '+18.2%' },
    { name: 'Automation Suite',   rev: '$6.7M',  delta: '+12.7%' },
    { name: 'Enterprise Onboard', rev: '$4.1M',  delta: '+9.1%'  },
  ];

  return (
    <Panel title="REVENUE INTELLIGENCE" badge="LIVE" style={{ flex: 1, minWidth:0 }}>
      <div className="rev-body">
        <div className="rev-overview">
          <div style={{ color: T.textDim, fontSize:10, letterSpacing:1 }}>REVENUE OVERVIEW</div>
          <div className="rev-total">
            <span style={{ color: T.gold, fontSize:22, fontWeight:800 }}>
              $24,590,483
            </span>
            <span className="rev-delta up">+12.5%</span>
          </div>
          <Sparkline values={[12,18,14,22,28,24,31,26,35,41,38,44]} color={T.gold} height={40} />
        </div>
        <div className="rev-by-source">
          <div style={{ color: T.textDim, fontSize:10, letterSpacing:1 }}>REVENUE BY SOURCE</div>
          <div className="rev-donut-placeholder">
            <svg width="80" height="80" viewBox="0 0 80 80">
              {[0,1,2,3].map((i) => {
                const [,,c] = data[i];
                const r = 30, cx=40, cy=40, sw=14;
                const pcts = [48,28,15,9];
                const total = pcts.reduce((a,b)=>a+b,0);
                const start = pcts.slice(0,i).reduce((a,b)=>a+b,0)/total;
                const end   = (start + pcts[i]/total);
                const sa = start*Math.PI*2 - Math.PI/2;
                const ea = end  *Math.PI*2 - Math.PI/2;
                const lx = cx + r*Math.cos(sa), ly = cy + r*Math.sin(sa);
                const rx = cx + r*Math.cos(ea), ry = cy + r*Math.sin(ea);
                const large = pcts[i]/total > 0.5 ? 1 : 0;
                return <path key={i}
                  d={`M${cx},${cy} L${lx},${ly} A${r},${r} 0 ${large},1 ${rx},${ry} Z`}
                  fill={c} opacity={0.7} stroke={T.bg} strokeWidth="1" />;
              })}
            </svg>
            <div className="donut-legend">
              {data.map(([label,pct,c]) => (
                <div key={label} className="donut-item">
                  <span style={{ color:c }}>■</span>
                  <span style={{ color: T.textDim, fontSize:9 }}>{label} {pct}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="rev-campaigns">
          <div style={{ color: T.textDim, fontSize:10, letterSpacing:1, marginBottom:6 }}>TOP PERFORMING CAMPAIGNS</div>
          {campaigns.map((c,i) => (
            <div key={i} className="campaign-row">
              <span className="camp-rank">◈</span>
              <span className="camp-name">{c.name}</span>
              <span style={{ color: T.gold, fontSize:12, fontWeight:700 }}>{c.rev}</span>
              <span className="rev-delta up" style={{ fontSize:10 }}>{c.delta}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function MissionTimeline({ tasks = [] }) {
  const phases = ['INTAKE','ANALYSIS','PLANNING','EXECUTION','VERIFICATION','COMPLETION'];
  const items = tasks.length ? tasks : [
    { name:'Lead Analysis Engine',   progress:0.85 },
    { name:'Market Research AI',     progress:0.60 },
    { name:'Content Generation',     progress:0.40 },
    { name:'Outreach Campaign',      progress:0.70 },
    { name:'Response Handling',      progress:0.50 },
    { name:'Conversion Pipeline',    progress:0.30 },
    { name:'Performance Analysis',   progress:0.20 },
  ];

  return (
    <Panel title="MISSION TIMELINE" badge="LIVE" style={{ flex: 1, minWidth:0 }}>
      <div className="timeline-phases">
        {phases.map((p,i) => (
          <div key={p} className="tl-phase">
            <div className="tl-phase-dot" style={{ background: i < 4 ? T.gold : T.textMuted }} />
            <span className="tl-phase-label">{p}</span>
          </div>
        ))}
      </div>
      <div className="timeline-items">
        {items.slice(0,7).map((item,i) => (
          <div key={i} className="tl-row">
            <span className="tl-name">{item.name}</span>
            <div className="tl-bar-track">
              <motion.div className="tl-bar-fill"
                initial={{ width:0 }}
                animate={{ width:`${item.progress*100}%` }}
                transition={{ duration:1, delay: i*0.1 }}
                style={{ background: `linear-gradient(90deg, ${T.gold}, ${T.goldDim})` }}
              />
            </div>
            <div className="tl-avatars">
              {[...Array(Math.floor(Math.random()*2+1))].map((_,j)=>(
                <div key={j} className="tl-avatar" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function SecurityCommandPanel() {
  const threats = ['Unusual login attempt blocked','Access policy violation detected','API rate limit exceeded','Suspicious data exfiltration attempt'];
  const times   = ['2m ago','5m ago','12m ago','18m ago'];

  return (
    <Panel title="SECURITY COMMAND CENTER" badge="LIVE" style={{ flex: 1, minWidth:0 }}>
      <div className="sec-body">
        <div className="sec-stats">
          <div className="sec-stat-block">
            <div style={{ color:T.textDim, fontSize:9, letterSpacing:1 }}>THREAT LEVEL</div>
            <div style={{ color:T.green, fontSize:16, fontWeight:800 }}>LOW</div>
          </div>
          <div className="sec-stat-block">
            <div style={{ color:T.textDim, fontSize:9, letterSpacing:1 }}>RISK EXPOSURE</div>
            <div style={{ color:T.gold, fontSize:16, fontWeight:800 }}>6.2%</div>
          </div>
          <div className="sec-stat-block">
            <div style={{ color:T.textDim, fontSize:9, letterSpacing:1 }}>ACTIVE THREATS</div>
            <div style={{ color:T.crimson, fontSize:16, fontWeight:800 }}>2</div>
          </div>
          <div className="sec-stat-block">
            <div style={{ color:T.textDim, fontSize:9, letterSpacing:1 }}>BLOCKED ATTACKS</div>
            <div style={{ color:T.gold, fontSize:16, fontWeight:800 }}>178</div>
          </div>
          <div className="sec-stat-block">
            <div style={{ color:T.textDim, fontSize:9, letterSpacing:1 }}>VULNERABILITIES</div>
            <div style={{ color:T.green, fontSize:16, fontWeight:800 }}>0</div>
          </div>
        </div>
        {/* World map placeholder */}
        <div className="sec-worldmap">
          <svg width="100%" height="60" viewBox="0 0 300 60" fill="none">
            <rect width="300" height="60" rx="2" fill="rgba(229,199,107,0.04)" stroke={T.border} strokeWidth="0.5"/>
            {[...Array(12)].map((_,i)=>(
              <circle key={i} cx={25+i*23} cy={20+Math.sin(i)*15} r={i%3===0?2.5:1.5}
                fill={i%5===0?T.crimson:T.gold} opacity={0.7} />
            ))}
            <text x="4" y="55" fill={T.textMuted} fontSize="7">GLOBAL THREAT MAP</text>
          </svg>
        </div>
        <div className="sec-events">
          <div style={{ color:T.textDim, fontSize:9, letterSpacing:1, marginBottom:4 }}>RECENT SECURITY EVENTS</div>
          {threats.map((t,i) => (
            <div key={i} className="sec-event">
              <span style={{ color: T.gold, marginRight:5 }}>⚠</span>
              <span style={{ color: T.text, fontSize:10, flex:1 }}>{t}</span>
              <span style={{ color: T.textDim, fontSize:9 }}>{times[i]}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

// ─── Bottom strip ─────────────────────────────────────────────────────────────
function BottomStrip({ onAction }) {
  const collaborators = ['AM','JL','SK','MR','TK'];
  const commands = ['+ NEW TASK','+ SPAWN AGENT','□ OPEN WORKSPACE','◉ SYSTEM SCAN','⚡ OPTIMIZE PERFORMANCE'];

  return (
    <div className="nexus-bottom-strip">
      <div className="bs-collaborators">
        <div style={{ color: T.textDim, fontSize:9, letterSpacing:1, marginBottom:4 }}>COLLABORATORS ONLINE</div>
        <div style={{ display:'flex', gap:4 }}>
          {collaborators.map((c,i) => (
            <div key={i} className="bs-avatar">{c[0]}</div>
          ))}
          <div className="bs-avatar bs-avatar-more">+3</div>
        </div>
      </div>
      <div className="bs-commands">
        <div style={{ color: T.textDim, fontSize:9, letterSpacing:1, marginBottom:4 }}>QUICK COMMANDS</div>
        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
          {commands.map(cmd => (
            <button key={cmd} className="bs-cmd-btn" onClick={() => onAction?.(cmd)}>{cmd}</button>
          ))}
        </div>
      </div>
      <div className="bs-voice">
        <div style={{ color: T.textDim, fontSize:9, letterSpacing:1, marginBottom:4 }}>VOICE COMMAND</div>
        <VoiceWaveform />
      </div>
    </div>
  );
}

function VoiceWaveform() {
  const bars = 24;
  const [amps, setAmps] = useState(() => Array.from({length:bars}, ()=>Math.random()*0.4+0.1));
  useEffect(() => {
    const id = setInterval(() => {
      setAmps(prev => prev.map(a => Math.max(0.05, Math.min(1, a + (Math.random()-0.5)*0.3))));
    }, 120);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{ display:'flex', alignItems:'center', gap:2, height:28 }}>
      <span style={{ color:T.gold, marginRight:4, fontSize:12 }}>🎙</span>
      {amps.map((a,i) => (
        <div key={i} style={{
          width:3, height: `${a*100}%`, borderRadius:2,
          background:`rgba(229,199,107,${0.3+a*0.7})`,
          transition:'height 0.12s ease',
        }} />
      ))}
    </div>
  );
}

// ─── Left status panel (System Status anatomical figure placeholder) ───────────
function SystemStatusPanel({ healthScore = 98.7 }) {
  return (
    <div className="nexus-system-status">
      <div className="ss-header">
        <span className="ss-dot active" />
        SYSTEM STATUS
        <button className="ss-close">×</button>
      </div>
      <div style={{ color:T.green, fontSize:9, letterSpacing:1, marginBottom:8 }}>ALL SYSTEMS OPERATIONAL</div>
      <div className="ss-figure">
        <svg width="60" height="100" viewBox="0 0 60 100" fill="none">
          <circle cx="30" cy="12" r="8" stroke={T.gold} strokeWidth="1" />
          <rect x="18" y="22" width="24" height="32" rx="4" stroke={T.gold} strokeWidth="1" fill="rgba(229,199,107,0.05)" />
          <line x1="18" y1="28" x2="6"  y2="50" stroke={T.gold} strokeWidth="1" />
          <line x1="42" y1="28" x2="54" y2="50" stroke={T.gold} strokeWidth="1" />
          <line x1="22" y1="54" x2="20" y2="90" stroke={T.gold} strokeWidth="1" />
          <line x1="38" y1="54" x2="40" y2="90" stroke={T.gold} strokeWidth="1" />
          {[...Array(6)].map((_,i)=>(
            <circle key={i} cx={15+Math.cos(i)*10} cy={30+i*4} r="1.5"
              fill={T.gold} opacity={0.3+Math.random()*0.5} />
          ))}
        </svg>
      </div>
      <div className="ss-score">
        <div style={{ color:T.textDim, fontSize:9, letterSpacing:1 }}>HEALTH SCORE</div>
        <div style={{ color:T.gold, fontSize:18, fontWeight:800 }}>{healthScore.toFixed(1)}%</div>
        <Sparkline values={[96,97,97,98,98,99,98,99,98,97,98,99]} color={T.gold} height={24} />
      </div>
    </div>
  );
}

// ─── Main dashboard ───────────────────────────────────────────────────────────
export function NexusOSDashboard() {
  const { sampleSystemStatus, agents = [], taskList = [] } = useAppStore();
  const [metrics, setMetrics] = useState({
    cpu:28, gpu:42, ram:71, vram:63, taskRate:0.5, load:0.5, thinking:0,
  });
  const [kpis, setKpis] = useState({
    revenue: 24590483,  revenue_delta:  12.5,
    agents:  102,       agents_delta:   8,
    tokens:  2460000,   tokens_delta:   18.7,
    uptime:  99.996,    uptime_delta:   0.001,
    tasks:   8429,      tasks_delta:    312,
    security:98.4,      security_delta: 0.6,
  });
  const [thinking, setThinking] = useState(false);

  // Poll real metrics
  useEffect(() => {
    const poll = () => {
      try {
        const s = sampleSystemStatus?.();
        if (s) setMetrics(m => ({
          ...m,
          cpu: s.cpuUsage ?? m.cpu,
          gpu: s.gpuUsage ?? m.gpu,
          ram: s.memoryUsage ?? m.ram,
          load: (s.cpuUsage ?? 50) / 100,
          taskRate: Math.min((s.tasksCompleted ?? 0) / Math.max(s.tasksTotal ?? 1, 1), 1),
        }));
      } catch (_) {}
    };
    poll();
    const id = setInterval(poll, 4000);
    return () => clearInterval(id);
  }, [sampleSystemStatus]);

  // Simulate slight KPI drift (replace with real API data)
  useEffect(() => {
    const id = setInterval(() => {
      setKpis(k => ({
        ...k,
        tasks:   k.tasks + Math.floor(Math.random() * 3),
        agents:  k.agents + (Math.random() > 0.7 ? 1 : 0),
        tokens:  k.tokens + Math.floor(Math.random() * 50000),
      }));
    }, 6000);
    return () => clearInterval(id);
  }, []);

  const handleAction = useCallback((cmd) => {
    if (cmd.includes('TASK') || cmd.includes('AGENT')) setThinking(true);
    setTimeout(() => setThinking(false), 8000);
  }, []);

  return (
    <div className="nexus-os">
      {/* KPI Strip */}
      <KPIStrip kpis={kpis} />

      {/* Main content: neural core + right column */}
      <div className="nexus-main">
        {/* Neural Command Core */}
        <div className="nexus-core-area">
          <div className="nexus-core-label">
            NEURAL COMMAND CORE <span className="nexus-badge">REAL-TIME</span>
          </div>
          {/* Node label overlay */}
          <div className="nexus-node-labels">
            {NODE_CONFIGS.map(n => {
              const x = 50 + Math.cos(n.angle) * 38;
              const y = 50 - Math.sin(n.angle) * 38;
              return (
                <div key={n.id} className="node-label-card" style={{
                  left:`${x}%`, top:`${y}%`,
                  borderColor: `rgba(${n.color.map(c=>Math.round(c*255)).join(',')},0.5)`,
                }}>
                  <div className="node-label-name">{n.label}</div>
                  <div className="node-label-pct" style={{ color:`rgb(${n.color.map(c=>Math.round(c*255)).join(',')})` }}>
                    {n.pct}
                  </div>
                  <div className="node-label-tps">{n.tps}</div>
                </div>
              );
            })}
          </div>
          <Canvas
            style={{ width:'100%', height:'100%', position:'absolute', inset:0 }}
            gl={{ antialias:true, alpha:true }}
            dpr={Math.min(window.devicePixelRatio, 2)}>
            <NeuralCoreScene metrics={metrics} />
          </Canvas>
          <SystemStatusPanel healthScore={98.7} />
        </div>

        {/* Right column */}
        <div className="nexus-right-col">
          <CognitionStream thinking={thinking} />
          <AgentSwarmHeatmap agents={agents} />
          <TelemetryPanel metrics={metrics} />
        </div>
      </div>

      {/* Bottom 3-panel row */}
      <div className="nexus-bottom-row">
        <RevenuePanel metrics={kpis} />
        <MissionTimeline tasks={taskList} />
        <SecurityCommandPanel />
      </div>

      {/* Bottom strip */}
      <BottomStrip onAction={handleAction} />
    </div>
  );
}

export default memo(NexusOSDashboard);
