import React, { useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import { useShaderMaterial, Float } from '@react-three/drei';
import * as THREE from 'three';
import coreVertShader from './shaders/core.vert.glsl';
import coreFragShader from './shaders/core.frag.glsl';

export const CoreSphere = ({ metrics = {} }) => {
  const meshRef = useRef();
  const materialRef = useRef();
  const startTimeRef = useRef(Date.now());

  const {
    rotationSpeed = 0.05,
    taskRate = 0.5,
    errorMix = 0.0,
    load = 0.5,
    thinking = 0.0,
  } = metrics;

  useEffect(() => {
    if (!materialRef.current) return;

    const uniforms = materialRef.current.uniforms;
    uniforms.u_taskRate.value = taskRate;
    uniforms.u_load.value = load;
    uniforms.u_errorMix.value = Math.min(errorMix, 1.0);
    uniforms.u_thinking.value = thinking;
  }, [taskRate, load, errorMix, thinking]);

  useFrame((state) => {
    if (!meshRef.current) return;

    const elapsed = (Date.now() - startTimeRef.current) * 0.001;

    // Rotate core
    meshRef.current.rotation.x += rotationSpeed * 0.0005;
    meshRef.current.rotation.y += rotationSpeed * 0.0008;

    // Update shader time
    if (materialRef.current) {
      materialRef.current.uniforms.u_time.value = elapsed;
    }
  });

  return (
    <Float speed={0.8} rotationIntensity={0.3} floatIntensity={0.1}>
      <mesh ref={meshRef} scale={1}>
        <icosahedronGeometry args={[1, 5]} />
        <shaderMaterial
          ref={materialRef}
          vertexShader={coreVertShader}
          fragmentShader={coreFragShader}
          uniforms={{
            u_time: { value: 0 },
            u_taskRate: { value: taskRate },
            u_load: { value: load },
            u_errorMix: { value: errorMix },
            u_thinking: { value: thinking },
          }}
          wireframe={false}
        />
      </mesh>
    </Float>
  );
};

export default CoreSphere;
