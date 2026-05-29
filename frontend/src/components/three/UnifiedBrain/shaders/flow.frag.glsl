// Flow edge fragment shader — colored packets with alpha fade at edges
varying float vProgress;
varying vec3 vColor;
uniform float u_time;
uniform float u_alpha;

void main() {
  // Circular point
  vec2 uv = gl_PointCoord - vec2(0.5);
  float dist = length(uv);
  if (dist > 0.5) discard;

  float alpha = (1.0 - dist * 2.0) * u_alpha;
  gl_FragColor = vec4(vColor, alpha);
}
