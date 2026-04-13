import { useState } from 'react'

interface Props {
  prompt: string | null
}

export default function PromptViewer({ prompt }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (!prompt) {
    return <div className="empty-state" style={{ height: 'auto' }}>No prompt data available</div>
  }

  // Highlight ## section headers
  const highlighted = prompt.split('\n').map((line, i) => {
    if (line.startsWith('## ')) {
      return <span key={i} className="prompt-section">{line}{'\n'}</span>
    }
    return <span key={i}>{line}{'\n'}</span>
  })

  return (
    <div className="section">
      <div className="section-header" onClick={() => setExpanded(!expanded)}>
        Full Prompt
        <span className="toggle">{expanded ? '\u25BC' : '\u25B6'}</span>
      </div>
      {expanded && (
        <div className="section-body">
          <div className="prompt-viewer">{highlighted}</div>
        </div>
      )}
    </div>
  )
}
