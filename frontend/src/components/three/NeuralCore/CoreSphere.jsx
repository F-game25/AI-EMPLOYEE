import React, { useRef, useEffect, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Float } from '@react-three/drei'
import * as THREE from 'three'
import coreVertShader from './shaders/core.vert.glsl'
import coreFragShader from './shaders/core.frag.glsl'
import { useAdaptiveQuality } from '../../../hooks/useAdaptiveQuality'
import { useActivityPulse } from './useActivityPulse'

const reducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export const CoreSphere = ({ metrics = {} }) => {
  const meshRef     = useRef()
  const materialRef = useRef()
  const startTimeRef = useRef(Date.now())
  const { particleCount } = useAdaptiveQuality()
  const rm = useMemo(reducedMotion, [])
  const { pulseIntensity, pulseColor, tick } = useActivityPulse(rm)

  const {
    rotationSpeed = 0.05,
    taskRate = 0.5,
    errorMix = 0.0,
    load = 0.5,
    thinking = 0.0,
  } = metrics

  useEffect(() => {
    if (!materialRef.current) return
    const u = materialRef.current.uniforms
    u.u_taskRate.value = taskRate
    u.u_load.value     = load
    u.u_errorMix.value = Math.min(errorMix, 1.0)
    u.u_thinking.value = thinking
  }, [taskRate, load, errorMix, thinking])

  useFrame((_, delta) => {
    if (!meshRef.current || document.hidden) return
    const elapsed = (Date.now() - startTimeRef.current) * 0.001

    meshRef.current.rotation.x += rotationSpeed * 0.0005
    meshRef.current.rotation.y += rotationSpeed * 0.0008

    if (materialRef.current) {
      tick(delta)
      const u = materialRef.current.uniforms
      u.u_time.value          = elapsed
      u.u_pulseIntensity.value = pulseIntensity.current
      u.u_pulseColor.value.copy(pulseColor.current)
    }
  })

  const geometryDetail = useMemo(() => {
    if (particleCount < 0.25) return 3
    if (particleCount < 0.5)  return 4
    return 5
  }, [particleCount])

  return (
    <Float speed={0.8} rotationIntensity={0.3} floatIntensity={0.1}>
      <mesh ref={meshRef} scale={1}>
        <icosahedronGeometry args={[1, geometryDetail]} />
        <shaderMaterial
          ref={materialRef}
          vertexShader={coreVertShader}
          fragmentShader={coreFragShader}
          uniforms={{
            u_time:          { value: 0 },
            u_taskRate:      { value: taskRate },
            u_load:          { value: load },
            u_errorMix:      { value: errorMix },
            u_thinking:      { value: thinking },
            u_pulseIntensity:{ value: 1.0 },
            u_pulseColor:    { value: new THREE.Color('#e5c76b') },
          }}
          wireframe={false}
        />
      </mesh>
    </Float>
  )
}

export default CoreSphere
