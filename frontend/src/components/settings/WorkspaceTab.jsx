import { useState } from 'react'
import { HexButton } from '../nexus-ui'
import { useFormState } from '../../hooks/useFormState'
import SettingsForm, { FormGroup, FormSection } from './SettingsForm'
import './WorkspaceTab.css'

const FILE_TYPES = ['.py', '.js', '.ts', '.jsx', '.tsx', '.md', '.txt', '.json', '.sh', '.css', '.html', '.sql']

const VALIDATORS = {
  max_file_size_mb: (val) => {
    const num = parseInt(val, 10)
    if (num < 1) return 'Minimum 1 MB'
    if (num > 1000) return 'Maximum 1000 MB'
    return null
  },
  max_files: (val) => {
    const num = parseInt(val, 10)
    if (num < 1 || num > 100) return 'Must be between 1-100'
    return null
  },
}

export default function WorkspaceTab({ settings = {}, onChange }) {
  const [clearedCache, setClearedCache] = useState(false)

  const form = useFormState(
    {
      max_file_size_mb: settings.max_file_size_mb || 50,
      max_files: settings.max_files || 20,
      allowed_file_types: settings.allowed_file_types || FILE_TYPES,
    },
    (key, val) => VALIDATORS[key]?.(val) || null
  )

  const handleFileTypeToggle = (fileType) => {
    const current = form.values.allowed_file_types || []
    const updated = current.includes(fileType)
      ? current.filter(t => t !== fileType)
      : [...current, fileType]
    form.setField('allowed_file_types', updated)
  }

  const handleClearCache = async () => {
    if (!window.confirm('Clear workspace cache? This cannot be undone.')) return

    try {
      const res = await fetch('/api/workspace/clear-cache', { method: 'POST' })
      if (res.ok) {
        setClearedCache(true)
        setTimeout(() => setClearedCache(false), 3000)
      }
    } catch (err) {
      console.error('Clear cache failed:', err)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (form.isValid()) {
      onChange?.(form.values)
    }
  }

  const allowedTypes = form.values.allowed_file_types || []

  return (
    <SettingsForm onSubmit={handleSubmit}>
      <FormSection title="File Configuration" description="Control upload limits and allowed file types">
        <FormGroup
          label="Max File Size (MB)"
          error={form.errors.max_file_size_mb}
          isTouched={form.touched.max_file_size_mb}
          hint="1-1000 MB"
          required
        >
          <input
            type="number"
            min="1"
            max="1000"
            {...form.getFieldProps('max_file_size_mb')}
          />
        </FormGroup>

        <FormGroup
          label="Max Files Per Upload"
          error={form.errors.max_files}
          isTouched={form.touched.max_files}
          hint="1-100 files"
          required
        >
          <input
            type="number"
            min="1"
            max="100"
            {...form.getFieldProps('max_files')}
          />
        </FormGroup>
      </FormSection>

      <FormSection title="Allowed File Types">
        <div className="workspace-file-types">
          {FILE_TYPES.map(fileType => (
            <label key={fileType} className="workspace-file-type-item">
              <input
                type="checkbox"
                checked={allowedTypes.includes(fileType)}
                onChange={() => handleFileTypeToggle(fileType)}
                className="workspace-file-type-checkbox"
              />
              <span className="workspace-file-type-label">{fileType}</span>
            </label>
          ))}
        </div>
      </FormSection>

      <FormSection title="Storage & Cache">
        <div className="workspace-storage-info">
          <div className="workspace-storage-item">
            <div className="workspace-storage-label">Default Storage Path</div>
            <div className="workspace-storage-value">~/.ai-employee/workspace</div>
          </div>
          <div className="workspace-storage-item">
            <div className="workspace-storage-label">Current Usage</div>
            <div className="workspace-storage-value">
              <div className="workspace-storage-bar">
                <div
                  className="workspace-storage-bar__fill"
                  style={{ width: '23%' }}
                  title="2.3 GB of 10 GB used"
                />
              </div>
              <div className="workspace-storage-text">2.3 GB / 10 GB</div>
            </div>
          </div>
        </div>

        <HexButton
          variant="outline"
          onClick={handleClearCache}
          tone={clearedCache ? 'gold' : undefined}
        >
          {clearedCache ? '✓ Cache Cleared' : 'Clear Cache'}
        </HexButton>
      </FormSection>
    </SettingsForm>
  )
}
