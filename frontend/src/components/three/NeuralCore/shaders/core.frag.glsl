// Core sphere fragment shader with Fresnel rim glow and subsurface effects
varying vec3 vNormal;
varying vec3 vPosition;
varying float vDisplacement;
varying float vThinking;

uniform float u_load;
uniform float u_errorMix;
uniform float u_thinking;

void main() {
  vec3 normal = normalize(vNormal);
  vec3 viewDir = normalize(-vPosition);

  // Fresnel effect for rim glow
  float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 3.0);

  // Base color: blend between card color and darker base
  vec3 baseColor = mix(vec3(0.048, 0.055, 0.098), vec3(0.165, 0.121, 0.039), u_load);

  // Error red bleed
  baseColor = mix(baseColor, vec3(0.8, 0.2, 0.2), u_errorMix * 0.6);

  // Thinking state: add purple glow
  vec3 thinkingColor = mix(baseColor, vec3(0.67, 0.33, 0.97), u_thinking * 0.3);

  // Rim glow (gold)
  vec3 rimColor = vec3(1.0, 0.85, 0.48);
  vec3 finalColor = mix(thinkingColor, rimColor, fresnel * 0.6);

  // Specular highlight
  vec3 lightDir = normalize(vec3(1.0, 1.0, 1.0));
  float spec = pow(max(dot(normal, lightDir), 0.0), 16.0);
  finalColor += rimColor * spec * 0.4;

  // Add glow based on displacement
  float glowAmount = vDisplacement * u_thinking * 2.0;
  finalColor += vec3(1.0, 0.85, 0.48) * glowAmount;

  gl_FragColor = vec4(finalColor, 1.0);
}
