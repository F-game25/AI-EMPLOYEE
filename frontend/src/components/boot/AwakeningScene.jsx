import React, { useEffect, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Sparkles, Text, Float } from '@react-three/drei';
import * as THREE from 'three';
import gsap from 'gsap';
import { useAudioBoot } from '../../hooks/useAudioBoot';
import './AwakeningScene.css';

export const AwakeningCore = () => {
  const { camera, scene } = useThree();
  const coreRef = useRef();
  const particlesRef = useRef();
  const octRef = useRef();
  const timelineRef = useRef(null);
  const [sequenceStarted, setSequenceStarted] = useState(false);

  const { playTimeline } = useAudioBoot();

  useEffect(() => {
    if (sequenceStarted) return;
    setSequenceStarted(true);

    const timeline = gsap.timeline();
    timelineRef.current = timeline;

    // t=0.0: Black void, horizon line
    gsap.set(scene.background, { color: 0x000000 });
    gsap.set(camera, { position: [0, 0, 3.5] });

    // t=0.4: Horizon ripple (core starts to glow)
    timeline.to(
      coreRef.current?.material,
      { emissiveIntensity: 0.3 },
      0.4
    );

    // t=1.2: Octahedron unfolds into sphere
    timeline.to(
      octRef.current?.scale,
      { x: 0, y: 0, z: 0 },
      1.2,
      '<'
    );

    // t=2.0: Core sphere tessellates (scale in)
    timeline.to(
      coreRef.current?.scale,
      { x: 1, y: 1, z: 1 },
      0.8,
      1.2
    );

    // t=3.5: First breath (scale + shockwave)
    timeline.to(
      coreRef.current?.scale,
      { x: 1.05, y: 1.05, z: 1.05 },
      0.4,
      3.1
    );
    timeline.to(
      coreRef.current?.scale,
      { x: 1.0, y: 1.0, z: 1.0 },
      0.4,
      3.5
    );

    // t=4.5: Synapses light (sequential node illumination)
    timeline.call(() => {
      // Nodes light up — handled in OrbitalNodes component
    }, [], 4.5);

    // t=6.0: System name reveal
    timeline.call(() => {
      // Text element handled in component
    }, [], 6.0);

    // t=7.5: Retina scan
    timeline.call(() => {
      const scanLine = document.createElement('div');
      scanLine.className = 'retina-scan-line';
      document.getElementById('awakening-overlay').appendChild(scanLine);
      setTimeout(() => scanLine.remove(), 500);
    }, [], 7.5);

    // t=8.0: Welcome message
    timeline.call(() => {
      const welcomeEl = document.querySelector('.welcome-text');
      if (welcomeEl) gsap.to(welcomeEl, { opacity: 1, duration: 0.5 });
    }, [], 8.0);

    // t=8.5: Dashboard reveal (camera dolly + fade boot sequence)
    timeline.to(
      camera,
      { position: [0, 0, 5.5], fov: 45 },
      1.5,
      8.5
    );

    timeline.call(() => {
      // Signal parent to show dashboard after boot
      window.dispatchEvent(new CustomEvent('boot-complete'));
    }, [], 10.0);

    playTimeline();
  }, [sequenceStarted, playTimeline, camera, scene]);

  useFrame(() => {
    if (coreRef.current) {
      coreRef.current.rotation.z += 0.0005;
    }
  });

  return (
    <>
      {/* Black void backdrop */}
      <mesh position={[0, 0, -2]}>
        <planeGeometry args={[100, 100]} />
        <meshBasicMaterial color="#000000" />
      </mesh>

      {/* Octahedron (unfolds at t=1.2) */}
      <mesh ref={octRef} scale={[0.6, 0.6, 0.6]}>
        <octahedronGeometry args={[1, 0]} />
        <meshPhongMaterial
          emissive="#e5c76b"
          emissiveIntensity={0.6}
          wireframe
          color="#1a1a2e"
        />
      </mesh>

      {/* Core sphere (grows from t=2.0) */}
      <mesh ref={coreRef} scale={[0, 0, 0]}>
        <icosahedronGeometry args={[1, 4]} />
        <meshPhongMaterial
          color="#0c0e18"
          emissive="#2a1f0a"
          emissiveIntensity={0.1}
          shininess={100}
          wireframe={false}
        />
      </mesh>

      {/* Sparkles (particle halo) */}
      <Sparkles
        count={100}
        scale={2}
        size={2}
        speed={0.5}
        color="#e5c76b"
      />

      {/* Orbital nodes (light up at t=4.5) */}
      <SequentialOrbitalNodes />

      {/* System name text (types in at t=6.0) */}
      <SystemNameText />
    </>
  );
};

const SequentialOrbitalNodes = () => {
  const nodesRef = useRef([]);
  const [illuminated, setIlluminated] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setIlluminated(prev => Math.min(prev + 1, 6));
    }, 300); // One node every 300ms starting at t=4.5

    return () => clearInterval(interval);
  }, []);

  const nodeData = [
    { angle: 0, color: '#e5c76b', label: 'Agents' },
    { angle: Math.PI / 3, color: '#a855f7', label: 'Memory' },
    { angle: (2 * Math.PI) / 3, color: '#cd7f32', label: 'Models' },
    { angle: Math.PI, color: '#ffdf00', label: 'Revenue' },
    { angle: (4 * Math.PI) / 3, color: '#8b0000', label: 'Security' },
    { angle: (5 * Math.PI) / 3, color: '#e8e8f0', label: 'Analytics' },
  ];

  return (
    <>
      {nodeData.map((node, idx) => {
        const x = Math.cos(node.angle) * 2.0;
        const z = Math.sin(node.angle) * 2.0;
        const isIlluminated = idx < illuminated;

        return (
          <mesh
            key={idx}
            position={[x, 0, z]}
            ref={el => {
              if (nodesRef.current) nodesRef.current[idx] = el;
            }}
          >
            <tetrahedronGeometry args={[0.2, 0]} />
            <meshPhongMaterial
              color={node.color}
              emissive={node.color}
              emissiveIntensity={isIlluminated ? 0.8 : 0.1}
            />
            <pointLight
              intensity={isIlluminated ? 1.5 : 0.3}
              distance={3}
              color={node.color}
            />
          </mesh>
        );
      })}
    </>
  );
};

const SystemNameText = () => {
  const textRef = useRef();
  const [displayText, setDisplayText] = useState('');

  useEffect(() => {
    const fullText = 'AI-EMPLOYEE';
    let charIndex = 0;

    // Start typing at t=6.0 (approximate, triggered by effect)
    const interval = setInterval(() => {
      if (charIndex <= fullText.length) {
        setDisplayText(fullText.slice(0, charIndex));
        charIndex++;
      } else {
        clearInterval(interval);
      }
    }, 80);

    return () => clearInterval(interval);
  }, []);

  return (
    <Text
      ref={textRef}
      position={[0, 1.5, 0]}
      fontSize={0.8}
      color="#e5c76b"
      anchorX="center"
      font="https://fonts.googleapis.com/css2?family=JetBrains+Mono&display=swap"
      maxWidth={5}
    >
      {displayText}
    </Text>
  );
};

export const AwakeningScene = () => {
  const [bootComplete, setBootComplete] = useState(false);

  useEffect(() => {
    const handleBootComplete = () => {
      setTimeout(() => setBootComplete(true), 500);
    };

    window.addEventListener('boot-complete', handleBootComplete);
    return () => window.removeEventListener('boot-complete', handleBootComplete);
  }, []);

  if (bootComplete) {
    return <div className="awakening-fade-out" />;
  }

  return (
    <div className="awakening-container">
      <Canvas
        camera={{ position: [0, 0, 3.5], fov: 50 }}
        style={{ width: '100vw', height: '100vh' }}
      >
        <ambientLight intensity={0.3} color="#1a1a2e" />
        <pointLight position={[5, 5, 5]} intensity={0.8} color="#e5c76b" />
        <AwakeningCore />
      </Canvas>

      <div id="awakening-overlay">
        <div className="horizon-line" />
        <div className="welcome-text">
          Welcome back, Operator
        </div>
      </div>
    </div>
  );
};

export default AwakeningScene;
