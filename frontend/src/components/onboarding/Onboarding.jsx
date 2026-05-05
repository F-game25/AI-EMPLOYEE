import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import './Onboarding.css';

/**
 * Onboarding Modal — one-time setup after AwakeningScene
 * Gated by identity.user_chosen === null
 * Captures: display name, instance name override, voice preset, color palette
 */

export const Onboarding = ({ onComplete }) => {
  const [step, setStep] = useState(0);
  const [displayName, setDisplayName] = useState('');
  const [instanceName, setInstanceName] = useState('');
  const [voicePreset, setVoicePreset] = useState('professional');
  const [colorPalette, setColorPalette] = useState(null);
  const [availablePalettes, setAvailablePalettes] = useState([]);
  const [loading, setLoading] = useState(false);

  // Fetch generated palettes from backend
  useEffect(() => {
    const fetchPalettes = async () => {
      try {
        const res = await fetch('/api/onboarding/palettes');
        if (res.ok) {
          const data = await res.json();
          setAvailablePalettes(data.palettes || []);
          if (data.palettes?.length > 0) {
            setColorPalette(data.palettes[0]);
          }
        }
      } catch (err) {
        console.error('Failed to fetch color palettes:', err);
      }
    };
    fetchPalettes();
  }, []);

  const handleNext = () => {
    if (step === 0 && !displayName.trim()) {
      alert('Please enter a display name');
      return;
    }
    setStep(step + 1);
  };

  const handleBack = () => {
    if (step > 0) setStep(step - 1);
  };

  const handleComplete = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/identity/finalize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_chosen: displayName || undefined,
          instance_name: instanceName || undefined,
          voice_preset: voicePreset,
          color_palette: colorPalette
        })
      });

      if (res.ok) {
        onComplete?.();
      } else {
        alert('Failed to save onboarding choices');
      }
    } catch (err) {
      console.error('Onboarding error:', err);
      alert('Error saving onboarding');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        className="onboarding-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.5 }}
      >
        <motion.div
          className="onboarding-modal"
          initial={{ scale: 0.8, y: 50 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.8, y: 50 }}
          transition={{ duration: 0.6 }}
        >
          <div className="onboarding-header">
            <h2>Welcome to AI-Employee</h2>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${((step + 1) / 4) * 100}%` }}
              />
            </div>
          </div>

          <AnimatePresence mode="wait">
            {step === 0 && (
              <motion.div
                key="step-0"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
                className="onboarding-step"
              >
                <h3>What's your name?</h3>
                <p>This is how I'll address you in conversations.</p>
                <input
                  type="text"
                  placeholder="e.g., Sarah, Alex, Jordan..."
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleNext()}
                  className="onboarding-input"
                  autoFocus
                />
              </motion.div>
            )}

            {step === 1 && (
              <motion.div
                key="step-1"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
                className="onboarding-step"
              >
                <h3>What should you be called?</h3>
                <p>Or leave blank for the auto-generated name.</p>
                <input
                  type="text"
                  placeholder="e.g., Aurora, Zenith..."
                  value={instanceName}
                  onChange={(e) => setInstanceName(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleNext()}
                  className="onboarding-input"
                  autoFocus
                />
              </motion.div>
            )}

            {step === 2 && (
              <motion.div
                key="step-2"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
                className="onboarding-step"
              >
                <h3>How should I sound?</h3>
                <p>This sets my tone in conversations.</p>
                <div className="voice-chips">
                  {['professional', 'friendly', 'creative', 'concise'].map((preset) => (
                    <button
                      key={preset}
                      className={`voice-chip ${voicePreset === preset ? 'active' : ''}`}
                      onClick={() => setVoicePreset(preset)}
                    >
                      {preset.charAt(0).toUpperCase() + preset.slice(1)}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}

            {step === 3 && (
              <motion.div
                key="step-3"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
                className="onboarding-step"
              >
                <h3>Pick your color accent</h3>
                <p>This customizes the visual theme.</p>
                <div className="color-palette-grid">
                  {availablePalettes.map((palette, idx) => (
                    <button
                      key={idx}
                      className={`palette-swatch ${
                        colorPalette?.primary === palette.primary ? 'selected' : ''
                      }`}
                      style={{
                        background: `linear-gradient(135deg, ${palette.primary}, ${palette.accent})`
                      }}
                      onClick={() => setColorPalette(palette)}
                      title={`Palette ${idx + 1}`}
                    />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="onboarding-footer">
            <button
              className="btn-secondary"
              onClick={handleBack}
              disabled={step === 0}
            >
              ← Back
            </button>
            {step < 3 ? (
              <button className="btn-primary" onClick={handleNext}>
                Next →
              </button>
            ) : (
              <button
                className="btn-primary"
                onClick={handleComplete}
                disabled={loading}
              >
                {loading ? 'Saving...' : 'Complete Setup'}
              </button>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default Onboarding;
