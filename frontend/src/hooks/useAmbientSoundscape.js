import { useEffect, useRef } from 'react';
import { moodEngine } from '../core/MoodEngine';

/**
 * useAmbientSoundscape — Web Audio API ambient soundscape driven by MoodEngine
 * Creates adaptive atmospheric background with:
 * - Base pad (fundamental mood tone)
 * - Activity ticks (indicate system events)
 * - Mood transitions (smooth frequency sweeps)
 */

export const useAmbientSoundscape = () => {
  const audioContextRef = useRef(null);
  const oscillatorsRef = useRef([]);
  const gainNodesRef = useRef({});
  const isPlayingRef = useRef(false);

  // Initialize audio context on first use
  useEffect(() => {
    const initAudio = () => {
      if (audioContextRef.current) return;

      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      audioContextRef.current = audioContext;

      // Resume context if suspended (required by browser autoplay policy)
      if (audioContext.state === 'suspended') {
        document.addEventListener('click', () => {
          audioContext.resume();
        }, { once: true });
      }
    };

    initAudio();

    return () => {
      // Cleanup on unmount
      oscillatorsRef.current.forEach(osc => {
        try { osc.stop(); } catch {}
      });
      oscillatorsRef.current = [];
    };
  }, []);

  const startAmbient = () => {
    const ctx = audioContextRef.current;
    if (!ctx || isPlayingRef.current) return;

    isPlayingRef.current = true;

    // Create master gain (0.1 so it's subtle)
    const masterGain = ctx.createGain();
    masterGain.gain.setValueAtTime(0, ctx.currentTime);
    masterGain.gain.linearRampToValueAtTime(0.1, ctx.currentTime + 1);
    masterGain.connect(ctx.destination);
    gainNodesRef.current.master = masterGain;

    // Base pad oscillator (low-frequency fundamental)
    const padOsc = ctx.createOscillator();
    const padGain = ctx.createGain();
    padOsc.type = 'sine';
    padOsc.frequency.setValueAtTime(55, ctx.currentTime); // A1
    padGain.gain.setValueAtTime(0.05, ctx.currentTime);
    padOsc.connect(padGain);
    padGain.connect(masterGain);
    padOsc.start(ctx.currentTime);
    oscillatorsRef.current.push(padOsc);
    gainNodesRef.current.pad = padGain;
    gainNodesRef.current.padOsc = padOsc;

    // Harmonic overtone (adds texture)
    const overtoneOsc = ctx.createOscillator();
    const overtoneGain = ctx.createGain();
    overtoneOsc.type = 'sine';
    overtoneOsc.frequency.setValueAtTime(110, ctx.currentTime); // A2
    overtoneGain.gain.setValueAtTime(0.02, ctx.currentTime);
    overtoneOsc.connect(overtoneGain);
    overtoneGain.connect(masterGain);
    overtoneOsc.start(ctx.currentTime);
    oscillatorsRef.current.push(overtoneOsc);
    gainNodesRef.current.overtone = overtoneGain;
    gainNodesRef.current.overtoneOsc = overtoneOsc;

    // Ambient filter for warmth
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(400, ctx.currentTime);
    masterGain.connect(filter);
    filter.connect(ctx.destination);
  };

  const stopAmbient = () => {
    if (!isPlayingRef.current) return;

    const ctx = audioContextRef.current;
    const masterGain = gainNodesRef.current.master;

    // Fade out over 1 second
    if (masterGain) {
      masterGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 1);
    }

    setTimeout(() => {
      oscillatorsRef.current.forEach(osc => {
        try { osc.stop(); } catch {}
      });
      oscillatorsRef.current = [];
      gainNodesRef.current = {};
      isPlayingRef.current = false;
    }, 1000);
  };

  const updateMood = () => {
    const ctx = audioContextRef.current;
    if (!ctx || !isPlayingRef.current) return;

    const blendedMood = moodEngine.getBlendedMood();
    const { ambient_pad_freq } = blendedMood;

    // Smoothly transition pad frequency to match mood
    const padOsc = gainNodesRef.current.padOsc;
    if (padOsc) {
      padOsc.frequency.exponentialRampToValueAtTime(ambient_pad_freq, ctx.currentTime + 0.5);
    }

    // Overtone frequency (harmonic)
    const overtoneOsc = gainNodesRef.current.overtoneOsc;
    if (overtoneOsc) {
      overtoneOsc.frequency.exponentialRampToValueAtTime(ambient_pad_freq * 2, ctx.currentTime + 0.5);
    }
  };

  const playActivityTick = () => {
    const ctx = audioContextRef.current;
    if (!ctx) return;

    // Short beep-like sound for system events
    const tickOsc = ctx.createOscillator();
    const tickGain = ctx.createGain();

    tickOsc.type = 'sine';
    tickOsc.frequency.setValueAtTime(800, ctx.currentTime);
    tickOsc.frequency.exponentialRampToValueAtTime(600, ctx.currentTime + 0.05);

    tickGain.gain.setValueAtTime(0.08, ctx.currentTime);
    tickGain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);

    tickOsc.connect(tickGain);
    tickGain.connect(gainNodesRef.current.master || ctx.destination);

    tickOsc.start(ctx.currentTime);
    tickOsc.stop(ctx.currentTime + 0.1);
  };

  const playMoodTransition = () => {
    const ctx = audioContextRef.current;
    if (!ctx) return;

    // Chord-like sweep for mood changes
    const baseFreqs = [220, 330, 440]; // A3, E4, A4

    baseFreqs.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(freq * 1.2, ctx.currentTime + 0.2);

      gain.gain.setValueAtTime(0, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0.04, ctx.currentTime + 0.05);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.3);

      osc.connect(gain);
      gain.connect(gainNodesRef.current.master || ctx.destination);

      osc.start(ctx.currentTime + idx * 0.05);
      osc.stop(ctx.currentTime + 0.3);
    });
  };

  return {
    startAmbient,
    stopAmbient,
    updateMood,
    playActivityTick,
    playMoodTransition,
  };
};

export default useAmbientSoundscape;
