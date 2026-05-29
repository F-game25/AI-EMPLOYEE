import React, { useEffect, useRef, useState } from 'react';
import { Line, useCursor } from '@react-three/drei';
import * as THREE from 'three';

export const DataStreamHighway = ({ metrics = {} }) => {
  const beamsRef = useRef([]);
  const [beams, setBeams] = useState([]);

  const streamTypes = [
    { id: 'api', label: 'API', color: '#e5c76b', x: -1.5, speed: 2.0 },
    { id: 'agents', label: 'Agents', color: '#a855f7', x: -0.75, speed: 1.8 },
    { id: 'memory', label: 'Memory', color: '#cd7f32', x: 0, speed: 1.5 },
    { id: 'revenue', label: 'Revenue', color: '#ffdf00', x: 0.75, speed: 2.2 },
    { id: 'security', label: 'Security', color: '#8b0000', x: 1.5, speed: 1.3 },
    { id: 'evolution', label: 'Evolution', color: '#00ff88', x: 2.25, speed: 1.6 },
    { id: 'communication', label: 'Communication', color: '#00d4ff', x: 3.0, speed: 1.4 },
  ];

  useEffect(() => {
    setBeams(
      streamTypes.map(stream => ({
        ...stream,
        particles: Array.from({ length: 8 }, (_, i) => ({
          id: i,
          progress: (i / 8) * 100,
        })),
      }))
    );
  }, []);

  return (
    <>
      {beams.map(beam => (
        <DataStreamBeam key={beam.id} beam={beam} />
      ))}
    </>
  );
};

const DataStreamBeam = ({ beam }) => {
  const particlesRef = useRef([]);
  const frameRef = useRef(0);

  const frame = () => {
    frameRef.current += 1;
    particlesRef.current.forEach((mesh, idx) => {
      if (!mesh) return;

      const progress = (frameRef.current * beam.speed) % 100;
      const normalizedProgress = progress / 100;

      // Particle travels from left (z=-5) to right (z=5) in z-axis
      mesh.position.z = -5 + normalizedProgress * 10;

      // Subtle bobbing
      mesh.position.y = Math.sin(frameRef.current * 0.02 + idx * Math.PI / 4) * 0.1;

      // Fade in at start, out at end
      const alpha = normalizedProgress < 0.1 ? normalizedProgress * 10 : normalizedProgress > 0.9 ? (1 - normalizedProgress) * 10 : 1;
      mesh.material.opacity = alpha * 0.6;
    });
  };

  useEffect(() => {
    let rafId
    const loop = () => {
      rafId = requestAnimationFrame(loop)
      if (!document.hidden) frame()
    }
    rafId = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(rafId)
  }, [beam.speed]);

  return (
    <group position={[beam.x, 0, 0]}>
      {/* Beam line */}
      <Line
        points={[[-5, 0, 0], [5, 0, 0]]}
        color={beam.color}
        lineWidth={1}
        opacity={0.2}
        dashed={false}
      />

      {/* Particles (8 traveling along the beam) */}
      {[0, 1, 2, 3, 4, 5, 6, 7].map(idx => (
        <mesh
          key={idx}
          ref={el => {
            particlesRef.current[idx] = el;
          }}
          position={[-5 + (idx / 8) * 10, 0, 0]}
        >
          <sphereGeometry args={[0.08, 16, 16]} />
          <meshStandardMaterial
            color={beam.color}
            emissive={beam.color}
            emissiveIntensity={0.8}
            toneMapped={false}
            transparent
            opacity={0.6}
          />
        </mesh>
      ))}

      {/* Data label (at origin) */}
      <DataStreamLabel label={beam.label} color={beam.color} />

      {/* Origin marker (glow point) */}
      <mesh position={[-5, 0, 0]}>
        <sphereGeometry args={[0.15, 8, 8]} />
        <meshBasicMaterial color={beam.color} toneMapped={false} />
        <pointLight color={beam.color} intensity={0.8} distance={1} />
      </mesh>
    </group>
  );
};

const DataStreamLabel = ({ label, color }) => {
  const canvasRef = useRef(document.createElement('canvas'));

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    canvas.width = 256;
    canvas.height = 64;

    // Transparent background
    ctx.fillStyle = 'transparent';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Label text
    ctx.font = "bold 24px 'JetBrains Mono'";
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, canvas.width / 2, canvas.height / 2);

    // Create texture
  }, [label, color]);

  return (
    <mesh position={[-5.5, 0.3, 0]} scale={[0.5, 0.125, 1]}>
      <planeGeometry args={[4, 1]} />
      <meshBasicMaterial
        transparent
        depthWrite={false}
        color={color}
        opacity={0.3}
      />
    </mesh>
  );
};

export default DataStreamHighway;
