import React, { useRef, useMemo, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

export const ParticleCloud = ({ count = 5000, metrics = {} }) => {
  const pointsRef = useRef();
  const { taskRate = 0.5, activeAgents = 0 } = metrics;

  const geometry = useMemo(() => {
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const radius = 1.2 + Math.random() * 1.2;
      const height = (Math.random() - 0.5) * 2.4;

      positions[i * 3] = Math.cos(angle) * radius;
      positions[i * 3 + 1] = height;
      positions[i * 3 + 2] = Math.sin(angle) * radius;

      // Color: mostly gold, with purple/cyan speckles
      const rand = Math.random();
      if (rand < 0.85) {
        // Gold
        colors[i * 3] = 1.0;
        colors[i * 3 + 1] = 0.85;
        colors[i * 3 + 2] = 0.48;
      } else if (rand < 0.93) {
        // Purple
        colors[i * 3] = 0.67;
        colors[i * 3 + 1] = 0.33;
        colors[i * 3 + 2] = 0.97;
      } else {
        // Cyan
        colors[i * 3] = 0.24;
        colors[i * 3 + 1] = 0.91;
        colors[i * 3 + 2] = 1.0;
      }

      // Orbital velocity
      velocities[i * 3] = Math.cos(angle + Math.PI / 2) * 0.5;
      velocities[i * 3 + 1] = (Math.random() - 0.5) * 0.2;
      velocities[i * 3 + 2] = Math.sin(angle + Math.PI / 2) * 0.5;
    }

    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geom.setAttribute('velocity', new THREE.BufferAttribute(velocities, 3));

    return geom;
  }, [count]);

  const material = useMemo(
    () =>
      new THREE.PointsMaterial({
        size: 0.04,
        sizeAttenuation: true,
        vertexColors: true,
        transparent: true,
        opacity: 0.8,
      }),
    []
  );

  useFrame(() => {
    if (!pointsRef.current) return;

    const positions = pointsRef.current.geometry.attributes.position.array;
    const velocities = pointsRef.current.geometry.attributes.velocity.array;

    // Update particle positions
    for (let i = 0; i < count; i++) {
      positions[i * 3] += velocities[i * 3] * 0.01 * taskRate;
      positions[i * 3 + 1] += velocities[i * 3 + 1] * 0.01 * taskRate;
      positions[i * 3 + 2] += velocities[i * 3 + 2] * 0.01 * taskRate;

      // Wrap around
      const r = Math.sqrt(
        positions[i * 3] ** 2 + positions[i * 3 + 2] ** 2
      );
      if (r > 3.0) {
        const angle = Math.atan2(positions[i * 3 + 2], positions[i * 3]);
        const newRadius = 1.2 + Math.random() * 0.5;
        positions[i * 3] = Math.cos(angle) * newRadius;
        positions[i * 3 + 2] = Math.sin(angle) * newRadius;
      }
    }

    pointsRef.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pointsRef} geometry={geometry} material={material} />
  );
};

export default ParticleCloud;
