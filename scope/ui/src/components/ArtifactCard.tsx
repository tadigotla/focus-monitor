import { useState } from 'react'
import type { Artifact } from '../api/types'

interface Props {
  artifact: Artifact
  index: number
  screenshotPath?: string
}

const FIELDS: [keyof Artifact, string][] = [
  ['app', 'app'],
  ['workspace', 'workspace'],
  ['active_file', 'active file'],
  ['terminal_cwd', 'terminal cwd'],
  ['browser_url', 'browser url'],
]

export default function ArtifactCard({ artifact, index, screenshotPath }: Props) {
  const [imgError, setImgError] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const imgSrc = screenshotPath
    ? `/api/screenshot?path=${encodeURIComponent(screenshotPath)}`
    : null

  return (
    <div className="artifact-card">
      <div
        style={{
          fontWeight: 600, marginBottom: 6, fontSize: 12,
          color: 'var(--color-text-muted)',
          cursor: imgSrc ? 'pointer' : 'default',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}
        onClick={() => imgSrc && setExpanded(!expanded)}
      >
        <span>Screenshot {index + 1}</span>
        {imgSrc && (
          <span style={{ fontSize: 10 }}>{expanded ? '\u25BC' : '\u25B6'} image</span>
        )}
      </div>

      {expanded && imgSrc && !imgError && (
        <div style={{ marginBottom: 8 }}>
          <img
            src={imgSrc}
            alt={`Screenshot ${index + 1}`}
            onError={() => setImgError(true)}
            style={{
              width: '100%',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
            }}
          />
        </div>
      )}
      {expanded && imgError && (
        <div style={{
          marginBottom: 8, padding: 12, textAlign: 'center',
          background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)',
          fontSize: 12, color: 'var(--color-text-subtle)',
        }}>
          Screenshot unavailable (may have been cleaned up)
        </div>
      )}

      {FIELDS.map(([key, label]) => {
        const value = artifact[key]
        if (value === null || value === undefined) return null
        return (
          <div key={key} className="field">
            <span className="field-label">{label}</span>
            <span className="field-value">{String(value)}</span>
          </div>
        )
      })}
      {artifact.browser_tab_titles && artifact.browser_tab_titles.length > 0 && (
        <div className="field">
          <span className="field-label">tabs</span>
          <span className="field-value">{artifact.browser_tab_titles.join(', ')}</span>
        </div>
      )}
      <div className="field">
        <span className="field-label">action</span>
        <span className="field-value">{artifact.one_line_action}</span>
      </div>
      {screenshotPath && (
        <div className="screenshot-path">{screenshotPath}</div>
      )}
    </div>
  )
}
