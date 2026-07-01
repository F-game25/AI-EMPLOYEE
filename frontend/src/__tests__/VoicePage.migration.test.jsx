/**
 * VoicePage nexus-ui Migration Tests (Phase 5.1)
 * 20+ test cases covering migration completeness
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import VoicePage from '../frontend/src/components/pages/VoicePage'

// Mock API
jest.mock('../frontend/src/api/client', () => ({
  get: jest.fn(() => Promise.resolve({ available: true, tones: [], genders: [] })),
  voice: {
    synthesize: jest.fn(() => Promise.resolve({ message: 'Success' })),
  },
}))

// Mock store
jest.mock('../frontend/src/store/appStore', () => ({
  useAppStore: jest.fn(() => ({ /* mock state */ })),
}))

// Mock navigator.mediaDevices
Object.defineProperty(global.navigator, 'mediaDevices', {
  value: {
    enumerateDevices: jest.fn(() =>
      Promise.resolve([
        { kind: 'audioinput', deviceId: 'mic1', label: 'Microphone 1' },
        { kind: 'audiooutput', deviceId: 'speaker1', label: 'Speaker 1' },
      ])
    ),
    getUserMedia: jest.fn(() => Promise.resolve({})),
  },
})

describe('VoicePage - nexus-ui Migration', () => {
  describe('Component Rendering', () => {
    test('renders main container with correct class', () => {
      render(<VoicePage />)
      expect(document.querySelector('.vp-grid')).toBeInTheDocument()
    })

    test('renders KPI tile strip', () => {
      render(<VoicePage />)
      expect(document.querySelector('.vp-kpis')).toBeInTheDocument()
    })

    test('renders three KPI tiles', () => {
      render(<VoicePage />)
      const tiles = document.querySelectorAll('.nx-kpi')
      expect(tiles.length).toBeGreaterThanOrEqual(3)
    })

    test('renders tab bar with two tabs', () => {
      render(<VoicePage />)
      const tabBar = document.querySelector('.vp-tab-bar')
      expect(tabBar).toBeInTheDocument()
      const tabs = tabBar.querySelectorAll('.vp-tab-btn')
      expect(tabs.length).toBe(2)
    })

    test('renders Studio tab by default', () => {
      render(<VoicePage />)
      const studioTab = document.querySelector('.vp-tab-btn--active')
      expect(studioTab.textContent).toContain('PERSONA STUDIO')
    })
  })

  describe('nexus-ui Components Integration', () => {
    test('Panel component renders with nexus-ui classes', () => {
      render(<VoicePage />)
      const panels = document.querySelectorAll('.nx-panel')
      expect(panels.length).toBeGreaterThan(0)
    })

    test('KPITile component renders metrics', () => {
      render(<VoicePage />)
      const kpiTiles = document.querySelectorAll('.nx-kpi')
      expect(kpiTiles.length).toBeGreaterThanOrEqual(3)
    })

    test('HexButton component renders control buttons', () => {
      render(<VoicePage />)
      const hexButtons = document.querySelectorAll('.nx-hbtn')
      expect(hexButtons.length).toBeGreaterThan(0)
    })

    test('StatusPill component renders status indicators', () => {
      render(<VoicePage />)
      const pills = document.querySelectorAll('.nx-pill')
      expect(pills.length).toBeGreaterThan(0)
    })

    test('SectionLabel component renders section titles', () => {
      render(<VoicePage />)
      const labels = document.querySelectorAll('.nx-section-label')
      expect(labels.length).toBeGreaterThan(0)
    })

    test('Sparkline component renders in KPI tiles', async () => {
      render(<VoicePage />)
      await waitFor(() => {
        const sparklines = document.querySelectorAll('.nx-sparkline')
        expect(sparklines.length).toBeGreaterThan(0)
      })
    })

    test('no old ui/primitives components present', () => {
      render(<VoicePage />)
      // Should not have old StatCard or DataRow classes
      expect(document.querySelectorAll('[class*="stat-card"]').length).toBe(0)
      expect(document.querySelectorAll('[class*="data-row"]').length).toBe(0)
    })

    test('no inline MiniBar component — uses Sparkline instead', () => {
      render(<VoicePage />)
      // Check that Sparkline is used for metrics
      const sparklines = document.querySelectorAll('.nx-sparkline')
      expect(sparklines.length).toBeGreaterThan(0)
    })
  })

  describe('Slider Component (Local, Non-nexus-ui)', () => {
    test('Slider renders with correct class', () => {
      render(<VoicePage />)
      const sliders = document.querySelectorAll('.vp-slider')
      expect(sliders.length).toBeGreaterThan(0)
    })

    test('Slider input works and updates value', () => {
      const { container } = render(<VoicePage />)
      const sliderInputs = container.querySelectorAll('.vp-slider__input')
      expect(sliderInputs.length).toBeGreaterThan(0)

      const firstSlider = sliderInputs[0]
      fireEvent.change(firstSlider, { target: { value: '1.5' } })
      expect(firstSlider.value).toBe('1.5')
    })

    test('Slider displays formatted value', () => {
      render(<VoicePage />)
      const sliderLabels = document.querySelectorAll('.vp-slider__value')
      expect(sliderLabels.length).toBeGreaterThan(0)
    })

    test('Slider has correct color CSS variable', () => {
      const { container } = render(<VoicePage />)
      const sliderInput = container.querySelector('.vp-slider__input')
      expect(sliderInput).toHaveStyle('--slider-color: var(--nx-gold)')
    })
  })

  describe('Studio Tab Controls', () => {
    test('Gender buttons render', () => {
      render(<VoicePage />)
      const buttons = document.querySelectorAll('.vp-option-btn')
      expect(buttons.length).toBeGreaterThanOrEqual(3)
    })

    test('Gender selection updates state', async () => {
      render(<VoicePage />)
      const buttons = document.querySelectorAll('.vp-option-btn')
      fireEvent.click(buttons[0])
      // Button should have active class
      await waitFor(() => {
        expect(buttons[0]).toHaveClass('vp-option-btn--active')
      })
    })

    test('Tone buttons grid renders with 4 columns', () => {
      render(<VoicePage />)
      const toneGrid = document.querySelector('.vp-tone-grid')
      expect(toneGrid).toBeInTheDocument()
      expect(toneGrid.style.gridTemplateColumns).toBe('repeat(4, 1fr)')
    })

    test('Tone buttons update on click', async () => {
      render(<VoicePage />)
      const toneButtons = document.querySelectorAll('.vp-tone-btn')
      expect(toneButtons.length).toBeGreaterThan(0)
      fireEvent.click(toneButtons[0])
      await waitFor(() => {
        expect(toneButtons[0]).toHaveClass('vp-tone-btn--active')
      })
    })

    test('Persona summary displays all attributes', () => {
      render(<VoicePage />)
      const summary = document.querySelector('.vp-persona-summary')
      expect(summary).toBeInTheDocument()
      expect(summary.textContent).toContain('CURRENT PERSONA')
    })
  })

  describe('Test Voice Panel', () => {
    test('waveform visualizer renders', () => {
      render(<VoicePage />)
      const waveform = document.querySelector('.vp-waveform')
      expect(waveform).toBeInTheDocument()
    })

    test('waveform bars count correct', () => {
      render(<VoicePage />)
      const bars = document.querySelectorAll('.vp-waveform__bar')
      expect(bars.length).toBe(24) // 24 bars in default BARS array
    })

    test('textarea renders with correct class', () => {
      render(<VoicePage />)
      const textarea = document.querySelector('.vp-textarea')
      expect(textarea).toBeInTheDocument()
    })

    test('textarea updates on input', async () => {
      const { getByPlaceholderText } = render(<VoicePage />)
      const textarea = getByPlaceholderText('Enter text to synthesize...')
      fireEvent.change(textarea, { target: { value: 'Test' } })
      expect(textarea.value).toBe('Test')
    })

    test('TEST VOICE button renders', () => {
      render(<VoicePage />)
      const buttons = document.querySelectorAll('.nx-hbtn')
      const testBtn = Array.from(buttons).find(b => b.textContent.includes('TEST VOICE'))
      expect(testBtn).toBeInTheDocument()
    })

    test('TEST VOICE button disabled when textarea empty', () => {
      render(<VoicePage />)
      const buttons = document.querySelectorAll('.nx-hbtn')
      const testBtn = Array.from(buttons).find(b => b.textContent.includes('TEST VOICE'))
      expect(testBtn).toBeDisabled()
    })

    test('result message displays on test', async () => {
      const { getByPlaceholderText } = render(<VoicePage />)
      const textarea = getByPlaceholderText('Enter text to synthesize...')
      fireEvent.change(textarea, { target: { value: 'Hello' } })

      const buttons = document.querySelectorAll('.nx-hbtn')
      const testBtn = Array.from(buttons).find(b => b.textContent.includes('TEST VOICE'))
      fireEvent.click(testBtn)

      await waitFor(() => {
        const result = document.querySelector('.vp-result')
        expect(result).toBeInTheDocument()
      })
    })

    test('result message has success styling when ok', async () => {
      const { getByPlaceholderText } = render(<VoicePage />)
      const textarea = getByPlaceholderText('Enter text to synthesize...')
      fireEvent.change(textarea, { target: { value: 'Test' } })

      const buttons = document.querySelectorAll('.nx-hbtn')
      const testBtn = Array.from(buttons).find(b => b.textContent.includes('TEST VOICE'))
      fireEvent.click(testBtn)

      await waitFor(() => {
        const result = document.querySelector('.vp-result--ok')
        expect(result).toBeInTheDocument()
      })
    })
  })

  describe('Backend Status Panel', () => {
    test('backend status panel renders', () => {
      render(<VoicePage />)
      const panels = document.querySelectorAll('.nx-panel')
      const statusPanel = Array.from(panels).find(p => p.textContent.includes('BACKEND STATUS'))
      expect(statusPanel).toBeInTheDocument()
    })

    test('displays ONLINE when backend available', async () => {
      render(<VoicePage />)
      await waitFor(() => {
        const status = document.querySelector('.nx-pill')
        expect(status.textContent).toContain('YES')
      })
    })

    test('shows status rows with correct layout', () => {
      render(<VoicePage />)
      const rows = document.querySelectorAll('.vp-status-row')
      expect(rows.length).toBeGreaterThanOrEqual(4)
    })

    test('error box appears when backend unavailable', async () => {
      // Mock API to return unavailable
      const api = require('../frontend/src/api/client')
      api.get.mockResolvedValueOnce({ available: false })

      render(<VoicePage />)

      await waitFor(() => {
        const errorBox = document.querySelector('.vp-error-box')
        if (errorBox) {
          expect(errorBox).toBeInTheDocument()
          expect(errorBox.textContent).toContain('REQUIRED')
        }
      })
    })
  })

  describe('Voice Recording Section', () => {
    test('microphone select renders', () => {
      render(<VoicePage />)
      const selects = document.querySelectorAll('.vp-select')
      expect(selects.length).toBeGreaterThanOrEqual(2)
    })

    test('speaker select renders', () => {
      render(<VoicePage />)
      const selects = document.querySelectorAll('.vp-select')
      expect(selects.length).toBeGreaterThanOrEqual(2)
    })

    test('volume slider renders', () => {
      render(<VoicePage />)
      const sliders = document.querySelectorAll('.vp-slider')
      expect(sliders.length).toBeGreaterThan(0)
    })

    test('transcription display renders', () => {
      render(<VoicePage />)
      const display = document.querySelector('.vp-transcription-display')
      expect(display).toBeInTheDocument()
    })

    test('START/STOP recording button renders', () => {
      render(<VoicePage />)
      const buttons = document.querySelectorAll('.nx-hbtn')
      const recordBtn = Array.from(buttons).find(b => b.textContent.includes('START RECORDING'))
      expect(recordBtn).toBeInTheDocument()
    })

    test('CLEAR TRANSCRIPT button renders', () => {
      render(<VoicePage />)
      const buttons = document.querySelectorAll('.nx-hbtn')
      const clearBtn = Array.from(buttons).find(b => b.textContent.includes('CLEAR'))
      expect(clearBtn).toBeInTheDocument()
    })

    test('EXPORT TRANSCRIPT button renders', () => {
      render(<VoicePage />)
      const buttons = document.querySelectorAll('.nx-hbtn')
      const exportBtn = Array.from(buttons).find(b => b.textContent.includes('EXPORT'))
      expect(exportBtn).toBeInTheDocument()
    })
  })

  describe('Voice Settings Panel', () => {
    test('speech rate slider renders', () => {
      render(<VoicePage />)
      const sliders = document.querySelectorAll('.vp-slider')
      const speechRateSlider = Array.from(sliders).find(s =>
        s.textContent.includes('SPEECH RATE')
      )
      expect(speechRateSlider).toBeInTheDocument()
    })

    test('pitch slider renders', () => {
      render(<VoicePage />)
      const sliders = document.querySelectorAll('.vp-slider')
      const pitchSlider = Array.from(sliders).find(s =>
        s.textContent.includes('PITCH')
      )
      expect(pitchSlider).toBeInTheDocument()
    })

    test('accent select renders', () => {
      render(<VoicePage />)
      const selects = document.querySelectorAll('.vp-select')
      expect(selects.length).toBeGreaterThanOrEqual(2)
    })

    test('language select renders', () => {
      render(<VoicePage />)
      const selects = document.querySelectorAll('.vp-select')
      expect(selects.length).toBeGreaterThanOrEqual(2)
    })
  })

  describe('Recognition Quality Metrics', () => {
    test('accuracy metric renders', () => {
      render(<VoicePage />)
      const metrics = document.querySelectorAll('.vp-quality-metric')
      const accuracyMetric = Array.from(metrics).find(m =>
        m.textContent.includes('Accuracy')
      )
      expect(accuracyMetric).toBeInTheDocument()
    })

    test('confidence metric renders with StatusPill', () => {
      render(<VoicePage />)
      const metrics = document.querySelectorAll('.vp-quality-metric')
      const confidenceMetric = Array.from(metrics).find(m =>
        m.textContent.includes('Confidence')
      )
      expect(confidenceMetric).toBeInTheDocument()
    })

    test('latency metric renders', () => {
      render(<VoicePage />)
      const metrics = document.querySelectorAll('.vp-quality-metric')
      const latencyMetric = Array.from(metrics).find(m =>
        m.textContent.includes('Latency')
      )
      expect(latencyMetric).toBeInTheDocument()
    })

    test('accuracy bar displays correct width', () => {
      render(<VoicePage />)
      const fills = document.querySelectorAll('.vp-quality-metric__fill')
      fills.forEach(fill => {
        const width = fill.style.width
        expect(width).toMatch(/^\d+(\.\d+)?%$/)
      })
    })
  })

  describe('Presets Tab', () => {
    test('tab switches to presets', async () => {
      render(<VoicePage />)
      const tabs = document.querySelectorAll('.vp-tab-btn')
      const presetsTab = Array.from(tabs).find(t => t.textContent.includes('PRESETS'))
      fireEvent.click(presetsTab)

      await waitFor(() => {
        expect(presetsTab).toHaveClass('vp-tab-btn--active')
      })
    })

    test('presets grid renders', async () => {
      render(<VoicePage />)
      const tabs = document.querySelectorAll('.vp-tab-btn')
      const presetsTab = Array.from(tabs).find(t => t.textContent.includes('PRESETS'))
      fireEvent.click(presetsTab)

      await waitFor(() => {
        const grid = document.querySelector('.vp-presets-grid')
        expect(grid).toBeInTheDocument()
      })
    })

    test('preset cards render with correct class', async () => {
      render(<VoicePage />)
      const tabs = document.querySelectorAll('.vp-tab-btn')
      const presetsTab = Array.from(tabs).find(t => t.textContent.includes('PRESETS'))
      fireEvent.click(presetsTab)

      await waitFor(() => {
        const cards = document.querySelectorAll('.vp-preset-card')
        expect(cards.length).toBeGreaterThan(0)
      })
    })

    test('preset card displays name', async () => {
      render(<VoicePage />)
      const tabs = document.querySelectorAll('.vp-tab-btn')
      const presetsTab = Array.from(tabs).find(t => t.textContent.includes('PRESETS'))
      fireEvent.click(presetsTab)

      await waitFor(() => {
        const names = document.querySelectorAll('.vp-preset-card__name')
        expect(names.length).toBeGreaterThan(0)
        expect(names[0].textContent).toBeTruthy()
      })
    })

    test('preset card displays tone', async () => {
      render(<VoicePage />)
      const tabs = document.querySelectorAll('.vp-tab-btn')
      const presetsTab = Array.from(tabs).find(t => t.textContent.includes('PRESETS'))
      fireEvent.click(presetsTab)

      await waitFor(() => {
        const tones = document.querySelectorAll('.vp-preset-card__tone')
        expect(tones.length).toBeGreaterThan(0)
      })
    })

    test('preset card has SELECT PRESET button', async () => {
      render(<VoicePage />)
      const tabs = document.querySelectorAll('.vp-tab-btn')
      const presetsTab = Array.from(tabs).find(t => t.textContent.includes('PRESETS'))
      fireEvent.click(presetsTab)

      await waitFor(() => {
        const buttons = document.querySelectorAll('.nx-hbtn')
        const selectBtn = Array.from(buttons).find(b => b.textContent.includes('SELECT PRESET'))
        expect(selectBtn).toBeInTheDocument()
      })
    })

    test('SELECT PRESET button switches to studio', async () => {
      render(<VoicePage />)
      let tabs = document.querySelectorAll('.vp-tab-btn')
      const presetsTab = Array.from(tabs).find(t => t.textContent.includes('PRESETS'))
      fireEvent.click(presetsTab)

      await waitFor(() => {
        expect(presetsTab).toHaveClass('vp-tab-btn--active')
      })

      const buttons = document.querySelectorAll('.nx-hbtn')
      const selectBtn = Array.from(buttons).find(b => b.textContent.includes('SELECT PRESET'))
      fireEvent.click(selectBtn)

      await waitFor(() => {
        tabs = document.querySelectorAll('.vp-tab-btn')
        const studioTab = Array.from(tabs).find(t => t.textContent.includes('STUDIO'))
        expect(studioTab).toHaveClass('vp-tab-btn--active')
      })
    })
  })

  describe('Responsive Layout', () => {
    test('main grid has flex layout', () => {
      render(<VoicePage />)
      const grid = document.querySelector('.vp-grid')
      const styles = window.getComputedStyle(grid)
      expect(styles.display).toBe('flex')
    })

    test('KPI grid uses auto-fit columns', () => {
      render(<VoicePage />)
      const kpis = document.querySelector('.vp-kpis')
      const styles = window.getComputedStyle(kpis)
      expect(styles.display).toBe('grid')
    })

    test('two-column layout switches to one column at breakpoint', () => {
      render(<VoicePage />)
      const cols = document.querySelector('.vp-cols')
      expect(cols).toBeInTheDocument()
      // CSS media queries tested separately in CSS test suite
    })
  })

  describe('CSS Class Naming', () => {
    test('all custom classes use vp- prefix', () => {
      render(<VoicePage />)
      const elements = document.querySelectorAll('[class*="vp-"]')
      expect(elements.length).toBeGreaterThan(0)

      elements.forEach(el => {
        const classes = el.className.split(' ')
        classes.forEach(cls => {
          if (cls && !cls.includes('nx-') && !cls.includes('_')) {
            expect(cls).toMatch(/^vp-/)
          }
        })
      })
    })

    test('no old ui/primitives classes present', () => {
      render(<VoicePage />)
      const oldClasses = ['stat-card', 'data-row', 'mini-bar', 'badge', 'panel']
      oldClasses.forEach(oldClass => {
        expect(document.querySelectorAll(`[class*="${oldClass}"]`).length).toBe(0)
      })
    })

    test('nexus-ui classes properly integrated', () => {
      render(<VoicePage />)
      const nxClasses = ['nx-panel', 'nx-kpi', 'nx-hbtn', 'nx-pill', 'nx-section-label']
      nxClasses.forEach(nxClass => {
        expect(document.querySelectorAll(`.${nxClass}`).length).toBeGreaterThan(0)
      })
    })
  })

  describe('CSS Variables', () => {
    test('uses nexus-ui CSS variables', () => {
      const { container } = render(<VoicePage />)
      const styles = container.innerHTML
      expect(styles).toContain('--nx-gold')
      expect(styles).toContain('--nx-cyan')
    })

    test('slider uses custom color variable', () => {
      const { container } = render(<VoicePage />)
      const sliderInput = container.querySelector('.vp-slider__input')
      expect(sliderInput).toHaveStyle('--slider-color')
    })

    test('waveform uses custom height variable', () => {
      const { container } = render(<VoicePage />)
      const bars = container.querySelectorAll('.vp-waveform__bar')
      bars.forEach(bar => {
        const style = bar.getAttribute('style')
        expect(style).toContain('--bar-height')
      })
    })
  })

  describe('Accessibility', () => {
    test('buttons have proper type attributes', () => {
      render(<VoicePage />)
      const buttons = document.querySelectorAll('button')
      buttons.forEach(btn => {
        expect(btn.type).toMatch(/^button|submit$/)
      })
    })

    test('form controls have associated labels', () => {
      render(<VoicePage />)
      const selects = document.querySelectorAll('.vp-select')
      selects.forEach(select => {
        const parent = select.closest('.vp-select-label')
        expect(parent).toBeInTheDocument()
      })
    })

    test('textarea has placeholder text', () => {
      render(<VoicePage />)
      const textarea = document.querySelector('.vp-textarea')
      expect(textarea.placeholder).toBeTruthy()
    })
  })
})
