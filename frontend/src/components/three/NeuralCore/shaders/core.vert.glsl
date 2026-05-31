// Core sphere vertex shader with Perlin-like noise displacement
varying vec3 vNormal;
varying vec3 vPosition;
varying float vDisplacement;
varying float vThinking;

uniform float u_time;
uniform float u_taskRate;
uniform float u_thinking;

// Simple hash for pseudo-random Perlin noise
float hash(float n) {
  return fract(sin(n) * 43758.5453123);
}

// Smooth Perlin-like noise
float noise(vec3 x) {
  vec3 p = floor(x);
  vec3 f = fract(x);
  f = f * f * (3.0 - 2.0 * f);

  float n = p.x + p.y * 157.0 + 113.0 * p.z;
  return mix(
    mix(
      mix(hash(n + 0.0), hash(n + 1.0), f.x),
      mix(hash(n + 157.0), hash(n + 158.0), f.x),
      f.y
    ),
    mix(
      mix(hash(n + 113.0), hash(n + 114.0), f.x),
      mix(hash(n + 270.0), hash(n + 271.0), f.x),
      f.y
    ),
    f.z
  );
}

void main() {
  vNormal = normalize(normalMatrix * normal);
  vPosition = position;

  // Displace based on thinking state and task rate
  float displacement = noise(position * 2.0 + u_time * 0.5) * u_taskRate * 0.15;
  displacement += noise(position * 4.0 + u_time * 0.3) * u_thinking * 0.08;

  vDisplacement = displacement;
  vThinking = u_thinking;

  vec3 displaced = position + normal * displacement;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
}
