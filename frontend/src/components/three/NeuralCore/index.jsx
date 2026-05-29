import React, { Suspense, useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import {
  OrbitControls,
  PerspectiveCamera,
} from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import { BlendFunction } from 'postprocessing';
import * as THREE from 'three';
import CoreSphere from './CoreSphere';
import ParticleCloud from './ParticleCloud';
import OrbitalNodes from './OrbitalNodes';
import DataStreamHighway from '../DataStreamHighway';

const Scene = ({ metrics }) => {
  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 0, 3.5]} fov={50} />
      <OrbitControls
        autoRotate={false}
        autoRotateSpeed={0.5}
        enableDamping
        dampingFactor={0.05}
        enableZoom
        zoomSpeed={0.5}
        enablePan={false}
      />

      {/* Lighting */}
      <ambientLight intensity={0.4} color={new THREE.Color('#1a1a2e')} />
      <pointLight position={[5, 5, 5]} intensity={0.8} color='#FFD97A' />
      <pointLight position={[-5, -5, 5]} intensity={0.4} color='#A855F7' />

      {/* Core components */}
      <Suspense fallback={null}>
        <CoreSphere metrics={metrics} />
        <ParticleCloud count={5000} metrics={metrics} />
        <OrbitalNodes metrics={metrics} />
        <DataStreamHighway metrics={metrics} />
      </Suspense>

      {/* Post-processing */}
      <EffectComposer>
        <Bloom
          blendFunction={BlendFunction.SCREEN}
          intensity={metrics.load * 1.5}
          luminanceThreshold={0.2}
          luminanceSmoothing={0.9}
        />
      </EffectComposer>
    </>
  );
};

export const NeuralCore = ({ metrics = {} }) => {
  const [canvasMetrics, setCanvasMetrics] = useState({
    rotationSpeed: 0.05,
    taskRate: 0.5,
    errorMix: 0.0,
    load: 0.5,
    thinking: 0.0,
    activeAgents: 0,
  });

  useEffect(() => {
    setCanvasMetrics((prev) => ({
      ...prev,
      ...metrics,
    }));
  }, [metrics]);

  return (
    <Canvas
      style={{
        width: '100%',
        height: '100%',
        background: 'radial-gradient(ellipse at center, #070810 0%, #050608 100%)',
      }}
      gl={{
        antialias: true,
        alpha: true,
        preserveDrawingBuffer: true,
      }}
      dpr={Math.min(window.devicePixelRatio, 2)}
    >
      <Scene metrics={canvasMetrics} />
    </Canvas>
  );
};

export default NeuralCore;
