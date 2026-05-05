import { useState, useRef, useCallback } from 'react'
import { HexButton, StatusPill } from '../nexus-ui'
import './FileUploadZone.css'

const ALLOWED_EXTS = ['py', 'js', 'ts', 'jsx', 'tsx', 'md', 'txt', 'json', 'sh', 'css', 'html', 'csv', 'yaml', 'yml']
const MAX_SIZE = 50 * 1024 * 1024 // 50MB

function getExt(name) { return (name.split('.').pop() || '').toLowerCase() }
function fmtSize(b) { return b < 1024 ? `${b}B` : b < 1048576 ? `${(b/1024).toFixed(1)}KB` : `${(b/1048576).toFixed(1)}MB` }

export default function FileUploadZone({ onUploadComplete, apiUrl }) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [currentFile, setCurrentFile] = useState(null)
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)

  const validateFile = useCallback((file) => {
    const ext = getExt(file.name)
    if (!ALLOWED_EXTS.includes(ext)) {
      return `Invalid file type. Allowed: ${ALLOWED_EXTS.join(', ')}`
    }
    if (file.size > MAX_SIZE) {
      return `File too large. Max ${fmtSize(MAX_SIZE)}.`
    }
    return null
  }, [])

  const uploadFile = useCallback(async (file) => {
    const err = validateFile(file)
    if (err) {
      setError(err)
      return
    }

    setError(null)
    setUploading(true)
    setCurrentFile(file.name)
    setUploadProgress(0)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const xhr = new XMLHttpRequest()
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100)
          setUploadProgress(pct)
        }
      })

      const uploadPromise = new Promise((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status === 200) {
            const resp = JSON.parse(xhr.responseText)
            resolve(resp)
          } else {
            reject(new Error(`Upload failed: ${xhr.status}`))
          }
        }
        xhr.onerror = () => reject(new Error('Upload error'))
        xhr.open('POST', `${apiUrl}/api/workspace/upload`)
        xhr.send(formData)
      })

      await uploadPromise
      setUploadProgress(100)
      setTimeout(() => {
        setUploading(false)
        setCurrentFile(null)
        setUploadProgress(0)
        onUploadComplete?.()
      }, 500)
    } catch (e) {
      setError(e.message || 'Upload failed')
      setUploading(false)
      setCurrentFile(null)
      setUploadProgress(0)
    }
  }, [validateFile, onUploadComplete, apiUrl])

  const handleDragEnter = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.target === e.currentTarget) {
      setIsDragging(false)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      uploadFile(files[0])
    }
  }

  const handleFileInput = (e) => {
    const files = e.target.files
    if (files.length > 0) {
      uploadFile(files[0])
    }
  }

  const handleBrowse = () => {
    fileInputRef.current?.click()
  }

  const handleRetry = () => {
    setError(null)
    setUploadProgress(0)
  }

  return (
    <div className="fuz-container">
      {uploading ? (
        <div className="fuz-uploading">
          <div className="fuz-progress-wrap">
            <div className="fuz-file-name">{currentFile}</div>
            <div className="fuz-progress-bar">
              <div className="fuz-progress-fill" style={{ width: `${uploadProgress}%` }} />
            </div>
            <div className="fuz-progress-text">{uploadProgress}%</div>
          </div>
        </div>
      ) : error ? (
        <div className="fuz-error">
          <div className="fuz-error-icon">!</div>
          <div className="fuz-error-text">{error}</div>
          <HexButton variant="outline" size="sm" onClick={handleRetry}>
            Retry
          </HexButton>
        </div>
      ) : (
        <div
          className={`fuz-zone ${isDragging ? 'fuz-zone--dragging' : ''}`}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <div className="fuz-zone-content">
            <div className="fuz-icon">📤</div>
            <div className="fuz-text">
              <div className="fuz-label">Drag files here or</div>
              <HexButton variant="ghost" size="sm" onClick={handleBrowse}>
                Browse
              </HexButton>
            </div>
            <div className="fuz-hint">
              .py, .js, .ts, .jsx, .tsx, .md, .txt, .json, .sh, .css, .html
              <br />
              Max size: {fmtSize(MAX_SIZE)}
            </div>
          </div>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        onChange={handleFileInput}
        style={{ display: 'none' }}
      />
    </div>
  )
}
