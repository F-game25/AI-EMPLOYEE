import React, { useCallback, useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import { BlendFunction } from 'postprocessing';
import * as THREE from 'three';
import { useOrbitChildNodes } from '../../hooks/useOrbitNodeInteraction';

/**
 * OrbitalSubsystem — Renders a subsystem's child orbital nodes
 * Displayed when a user clicks an orbital node to enter that subsystem's view
 * Shows 4 child satellites in orbital formation around a central marker
 */

export const OrbitalSubsystem = ({ nodeId, onExit }) => {
  const { children } = useOrbitChildNodes(nodeId);
  const [exitButtonVisible, setExitButtonVisible] = useState(true);

  const handleExit = () => {
    if (onExit) onExit();
    setExitButtonVisible(false);
  };

  const onCreated = useCallback(({ gl }) => {
    gl.domElement.addEventListener('webglcontextlost', e => e.preventDefault())
    gl.domElement.addEventListener('webglcontextrestored', () => gl.forceContextRestore?.())
  }, [])

  return (
    <div className="orbital-subsystem-container">
      <Canvas
        camera={{ position: [0, 0, 3.5], fov: 50 }}
        style={{ width: '100%', height: '100%' }}
        onCreated={onCreated}
      >
        <ambientLight intensity={0.3} color="#1a1a2e" />
        <pointLight position={[5, 5, 5]} intensity={0.8} color="#e5c76b" />
        <pointLight position={[-5, -5, 5]} intensity={0.4} color="#a855f7" />

        <OrbitControls
          autoRotate={false}
          enableDamping
          dampingFactor={0.05}
          enableZoom
          zoomSpeed={0.5}
        />

        <SubsystemScene children={children} />

        <EffectComposer>
          <Bloom blendFunction={BlendFunction.SCREEN} intensity={0.6} luminanceThreshold={0.2} luminanceSmoothing={0.9} />
        </EffectComposer>
      </Canvas>

      {exitButtonVisible && (
        <button className="orbital-exit-btn" onClick={handleExit} title="Return to core view">
          ⬅ RETURN TO CORE
        </button>
      )}

      <div className="orbital-subsystem-label">
        {nodeId.toUpperCase().replace('-', ' ')} SUBSYSTEM
      </div>
    </div>
  );
};

const SubsystemScene = ({ children }) => {
  return (
    <>
      {/* Central marker (glowing sphere) */}
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[0.3, 32, 32]} />
        <meshPhongMaterial
          color="#e5c76b"
          emissive="#e5c76b"
          emissiveIntensity={0.8}
        />
        <pointLight intensity={1.2} distance={2} color="#e5c76b" />
      </mesh>

      {/* Child orbital nodes */}
      {children.map((child, idx) => {
        const angle = (idx / children.length) * Math.PI * 2;
        const radius = 2.0;
        const x = Math.cos(angle) * radius;
        const z = Math.sin(angle) * radius;

        return (
          <group key={child.id} position={[x, 0, z]}>
            {/* Node mesh */}
            <mesh>
              <octahedronGeometry args={[0.25, 0]} />
              <meshPhongMaterial
                color={child.color}
                emissive={child.color}
                emissiveIntensity={0.6}
              />
              <pointLight
                intensity={0.8}
                distance={1.5}
                color={child.color}
              />
            </mesh>

            {/* Connecting line to center */}
            <line>
              <bufferGeometry>
                <bufferAttribute
                  attach="attributes-position"
                  count={2}
                  array={new Float32Array([-x, 0, -z, 0, 0, 0])}
                  itemSize={3}
                />
              </bufferGeometry>
              <lineBasicMaterial color={child.color} opacity={0.4} transparent />
            </line>

            {/* Label */}
            <mesh position={[0, 0.5, 0]}>
              <planeGeometry args={[1.5, 0.3]} />
              <meshBasicMaterial
                color={child.color}
                opacity={0.15}
                transparent
              />
            </mesh>
          </group>
        );
      })}
    </>
  );
};

export default OrbitalSubsystem;
