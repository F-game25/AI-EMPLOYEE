import { useEffect, useRef } from 'react';

export const useAudioBoot = () => {
  const audioContextRef = useRef(null);
  const oscillatorsRef = useRef([]);

  useEffect(() => {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    audioContextRef.current = audioContext;

    return () => {
      oscillatorsRef.current.forEach(osc => {
        try { osc.stop(); } catch {}
      });
      oscillatorsRef.current = [];
    };
  }, []);

  const playTimeline = () => {
    const ctx = audioContextRef.current;
    if (!ctx) return;

    const now = ctx.currentTime;

    // t=0.0: Deep sub hum (40Hz)
    const subOsc = ctx.createOscillator();
    const subGain = ctx.createGain();
    subOsc.frequency.value = 40;
    subGain.gain.setValueAtTime(0, now);
    subGain.gain.linearRampToValueAtTime(0.15, now + 0.3);
    subGain.gain.linearRampToValueAtTime(0, now + 1.0);
    subOsc.connect(subGain);
    subGain.connect(ctx.destination);
    subOsc.start(now);
    subOsc.stop(now + 1.0);
    oscillatorsRef.current.push(subOsc);

    // t=0.4: Soft tick (filtered noise burst)
    const tickNoise = ctx.createBufferSource();
    const noiseBuffer = ctx.createBuffer(1, ctx.sampleRate * 0.1, ctx.sampleRate);
    const noiseData = noiseBuffer.getChannelData(0);
    for (let i = 0; i < noiseData.length; i++) {
      noiseData[i] = Math.random() * 2 - 1;
    }
    tickNoise.buffer = noiseBuffer;
    const tickGain = ctx.createGain();
    const tickFilter = ctx.createBiquadFilter();
    tickFilter.type = 'highpass';
    tickFilter.frequency.value = 8000;
    tickGain.gain.setValueAtTime(0.1, now + 0.4);
    tickGain.gain.linearRampToValueAtTime(0, now + 0.5);
    tickNoise.connect(tickFilter);
    tickFilter.connect(tickGain);
    tickGain.connect(ctx.destination);
    tickNoise.start(now + 0.4);

    // t=1.2: Rising synth swell (300Hz → 800Hz over 1s)
    const swellOsc = ctx.createOscillator();
    const swellGain = ctx.createGain();
    swellOsc.type = 'sine';
    swellOsc.frequency.setValueAtTime(300, now + 1.2);
    swellOsc.frequency.exponentialRampToValueAtTime(800, now + 2.2);
    swellGain.gain.setValueAtTime(0, now + 1.2);
    swellGain.gain.linearRampToValueAtTime(0.2, now + 1.5);
    swellGain.gain.linearRampToValueAtTime(0, now + 2.2);
    swellOsc.connect(swellGain);
    swellGain.connect(ctx.destination);
    swellOsc.start(now + 1.2);
    swellOsc.stop(now + 2.2);
    oscillatorsRef.current.push(swellOsc);

    // t=2.0: Crystalline shimmer (high-pass white noise)
    const shimmerNoise = ctx.createBufferSource();
    const shimmerBuffer = ctx.createBuffer(1, ctx.sampleRate * 1.5, ctx.sampleRate);
    const shimmerData = shimmerBuffer.getChannelData(0);
    for (let i = 0; i < shimmerData.length; i++) {
      shimmerData[i] = Math.random() * 2 - 1;
    }
    shimmerNoise.buffer = shimmerBuffer;
    const shimmerGain = ctx.createGain();
    const shimmerFilter = ctx.createBiquadFilter();
    shimmerFilter.type = 'highpass';
    shimmerFilter.frequency.value = 12000;
    shimmerGain.gain.setValueAtTime(0, now + 2.0);
    shimmerGain.gain.linearRampToValueAtTime(0.15, now + 2.3);
    shimmerGain.gain.linearRampToValueAtTime(0, now + 3.5);
    shimmerNoise.connect(shimmerFilter);
    shimmerFilter.connect(shimmerGain);
    shimmerGain.connect(ctx.destination);
    shimmerNoise.start(now + 2.0);

    // t=3.5: Deep "thoom" sub-bass (50Hz pulse)
    const thoomOsc = ctx.createOscillator();
    const thoomGain = ctx.createGain();
    thoomOsc.frequency.value = 50;
    thoomGain.gain.setValueAtTime(0, now + 3.5);
    thoomGain.gain.linearRampToValueAtTime(0.3, now + 3.6);
    thoomGain.gain.linearRampToValueAtTime(0, now + 4.0);
    thoomOsc.connect(thoomGain);
    thoomGain.connect(ctx.destination);
    thoomOsc.start(now + 3.5);
    thoomOsc.stop(now + 4.0);
    oscillatorsRef.current.push(thoomOsc);

    // t=4.5: 6 ascending pentatonic pings
    const pentatonic = [329.63, 392.0, 493.88, 587.33, 659.25]; // C5-E5-G5-A5-B5
    [0, 1, 2, 3, 4, 5].forEach(idx => {
      setTimeout(() => {
        const pingOsc = ctx.createOscillator();
        const pingGain = ctx.createGain();
        const freq = pentatonic[idx % pentatonic.length];
        pingOsc.frequency.value = freq;
        pingGain.gain.setValueAtTime(0.15, ctx.currentTime);
        pingGain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
        pingOsc.connect(pingGain);
        pingGain.connect(ctx.destination);
        pingOsc.start(ctx.currentTime);
        pingOsc.stop(ctx.currentTime + 0.3);
      }, idx * 300); // One every 300ms
    });

    // t=6.0: Mechanical typewriter clicks (6 clicks, one per char in "AI-EMP")
    [0, 1, 2, 3, 4, 5].forEach(idx => {
      setTimeout(() => {
        const clickNoise = ctx.createBufferSource();
        const clickBuffer = ctx.createBuffer(1, ctx.sampleRate * 0.05, ctx.sampleRate);
        const clickData = clickBuffer.getChannelData(0);
        for (let i = 0; i < clickData.length; i++) {
          clickData[i] = (Math.random() * 2 - 1) * Math.exp(-(i / clickData.length) * 3);
        }
        clickNoise.buffer = clickBuffer;
        const clickGain = ctx.createGain();
        clickGain.gain.setValueAtTime(0.08, ctx.currentTime);
        clickGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.05);
        clickNoise.connect(clickGain);
        clickGain.connect(ctx.destination);
        clickNoise.start(ctx.currentTime);
      }, 6000 + idx * 80); // Start at t=6.0, one click every 80ms
    });

    // t=7.5: Subtle scanning beep (rising 1kHz → 3kHz sweep)
    const scanOsc = ctx.createOscillator();
    const scanGain = ctx.createGain();
    scanOsc.frequency.setValueAtTime(1000, now + 7.5);
    scanOsc.frequency.exponentialRampToValueAtTime(3000, now + 7.8);
    scanGain.gain.setValueAtTime(0.1, now + 7.5);
    scanGain.gain.linearRampToValueAtTime(0, now + 7.8);
    scanOsc.connect(scanGain);
    scanGain.connect(ctx.destination);
    scanOsc.start(now + 7.5);
    scanOsc.stop(now + 7.8);
    oscillatorsRef.current.push(scanOsc);

    // t=8.0: Warm ambient pad (sustained tone)
    const padOsc = ctx.createOscillator();
    const padGain = ctx.createGain();
    padOsc.type = 'sine';
    padOsc.frequency.value = 110; // A2
    padGain.gain.setValueAtTime(0, now + 8.0);
    padGain.gain.linearRampToValueAtTime(0.1, now + 8.2);
    padGain.gain.linearRampToValueAtTime(0.05, now + 9.0);
    padOsc.connect(padGain);
    padGain.connect(ctx.destination);
    padOsc.start(now + 8.0);
    padOsc.stop(now + 9.5);
    oscillatorsRef.current.push(padOsc);
  };

  return { playTimeline };
};
