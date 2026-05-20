// Flow edge vertex shader — UV-animated packet travel along edges
attribute float aProgress;
varying float vProgress;
varying vec3 vColor;
uniform float u_time;
uniform vec3 u_color;

void main() {
  vProgress = aProgress;
  vColor = u_color;
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = 4.0 * (1.0 / -mvPosition.z);
  gl_Position = projectionMatrix * mvPosition;
}
