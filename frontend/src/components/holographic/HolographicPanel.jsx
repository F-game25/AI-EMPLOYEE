import React, { useState, useRef } from 'react';
import { motion } from 'framer-motion';
import './HolographicPanel.css';

export const HolographicPanel = ({
  title,
  children,
  tone = 'gold',
  position = 'TL',
  onClose,
  isDraggable = true,
  isResizable = false,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [customPos, setCustomPos] = useState(null);
  const panelRef = useRef();

  const handleMouseDown = (e) => {
    if (!isDraggable) return;
    setIsDragging(true);
    setDragOffset({
      x: e.clientX - (customPos?.x || 0),
      y: e.clientY - (customPos?.y || 0),
    });
  };

  const handleMouseMove = (e) => {
    if (!isDragging) return;
    setCustomPos({
      x: e.clientX - dragOffset.x,
      y: e.clientY - dragOffset.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const positionClasses = {
    TL: 'panel-tl',
    T: 'panel-t',
    TR: 'panel-tr',
    L: 'panel-l',
    R: 'panel-r',
    BL: 'panel-bl',
    B: 'panel-b',
    BR: 'panel-br',
  };

  return (
    <motion.div
      ref={panelRef}
      className={`holographic-panel ${tone} ${positionClasses[position]}`}
      style={{
        left: customPos?.x,
        top: customPos?.y,
      }}
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      draggable={isDraggable}
    >
      {/* Backplate */}
      <div className='panel-backplate' />

      {/* Edge bevel */}
      <div className='panel-edge-bevel' />

      {/* Corner brackets */}
      <div className='panel-corner-brackets'>
        <div className='bracket tl' />
        <div className='bracket tr' />
        <div className='bracket bl' />
        <div className='bracket br' />
      </div>

      {/* Inner glow */}
      <div className='panel-inner-glow' />

      {/* Header */}
      <div className='panel-header' onMouseDown={handleMouseDown}>
        <div className='header-title'>{title}</div>
        <div className='header-controls'>
          {onClose && (
            <button className='btn-close' onClick={onClose}>
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Activity indicator */}
      <div className='panel-activity-indicator' />

      {/* Content */}
      <div className='panel-content'>{children}</div>

      {/* Scanline overlay */}
      <div className='panel-scanlines' />

      {/* Specular highlight */}
      <div className='panel-specular' />
    </motion.div>
  );
};

export default HolographicPanel;
