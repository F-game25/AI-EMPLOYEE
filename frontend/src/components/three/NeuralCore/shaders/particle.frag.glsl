// Particle fragment shader with trail effect
varying vec3 vColor;
varying float vLife;

void main() {
  // Circular particle with soft edges
  vec2 circCoord = 2.0 * gl_PointCoord - 1.0;
  float r = dot(circCoord, circCoord);
  if (r > 1.0) discard;

  // Fade toward edges and over lifetime
  float alpha = (1.0 - r) * vLife * 0.8;

  gl_FragColor = vec4(vColor, alpha);
}
