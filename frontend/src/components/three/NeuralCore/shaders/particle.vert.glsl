// GPU particle system vertex shader
attribute vec3 velocity;
attribute float agentId;
attribute float lifespan;
attribute vec3 color;

varying vec3 vColor;
varying float vLife;

uniform float u_time;
uniform float u_deltaTime;

void main() {
  // Simple orbital motion with life decay
  vec3 pos = position;

  // Orbital velocity
  vec3 orbital = normalize(velocity) * length(position) * 0.3;
  pos += orbital * u_deltaTime;

  // Slight drift
  pos += velocity * u_deltaTime * 0.5;

  // Life decay
  float age = mod(u_time, lifespan) / lifespan;
  vLife = 1.0 - age;
  vColor = color;

  gl_PointSize = 2.0 + (vLife * 1.5);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
