import React, { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text } from '@react-three/drei';
import * as THREE from 'three';

const nodeConfigs = [
  {
    id: 'agents',
    label: 'Agent Swarm',
    angle: 0,
    color: [1.0, 0.85, 0.48], // gold
    icon: '⬢',
  },
  {
    id: 'memory',
    label: 'Memory Universe',
    angle: Math.PI / 3,
    color: [0.67, 0.33, 0.97], // purple
    icon: '◉',
  },
  {
    id: 'models',
    label: 'Model Cluster',
    angle: (Math.PI * 2) / 3,
    color: [0.8, 0.5, 0.2], // bronze
    icon: '▲',
  },
  {
    id: 'revenue',
    label: 'Revenue Intelligence',
    angle: Math.PI,
    color: [1.0, 0.85, 0.48], // bright gold
    icon: '◆',
  },
  {
    id: 'security',
    label: 'Security Command',
    angle: Math.PI + Math.PI / 3,
    color: [0.8, 0.1, 0.1], // crimson
    icon: '■',
  },
  {
    id: 'analytics',
    label: 'Analytics Lab',
    angle: Math.PI + (Math.PI * 2) / 3,
    color: [0.8, 0.8, 0.9], // silver
    icon: '★',
  },
];

const OrbitalNode = ({ config, orbitRadius = 3.2, metrics = {} }) => {
  const groupRef = useRef();
  const meshRef = useRef();

  useFrame((state) => {
    if (!groupRef.current) return;

    const time = state.clock.getElapsedTime();
    const x = Math.cos(config.angle + time * 0.2) * orbitRadius;
    const z = Math.sin(config.angle + time * 0.2) * orbitRadius;

    groupRef.current.position.set(x, 0.5, z);

    // Rotate mesh
    if (meshRef.current) {
      meshRef.current.rotation.z += 0.01;
    }
  });

  return (
    <group ref={groupRef}>
      <mesh ref={meshRef}>
        <tetrahedronGeometry args={[0.25, 0]} />
        <meshStandardMaterial
          color={new THREE.Color(...config.color)}
          emissive={new THREE.Color(...config.color)}
          emissiveIntensity={0.6}
          wireframe={false}
        />
      </mesh>
      <pointLight
        intensity={0.8}
        distance={3}
        color={new THREE.Color(...config.color)}
      />
    </group>
  );
};

export const OrbitalNodes = ({ metrics = {} }) => {
  return (
    <>
      {nodeConfigs.map((config) => (
        <OrbitalNode key={config.id} config={config} metrics={metrics} />
      ))}
    </>
  );
};

export default OrbitalNodes;
