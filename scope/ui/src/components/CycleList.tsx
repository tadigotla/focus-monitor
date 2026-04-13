import { useEffect, useState } from 'react'
import type { Cycle } from '../api/types'
import { fetchCycles } from '../api/client'
import CycleListItem from './CycleListItem'

interface Props {
  date: string
  selectedId: number | null
  onSelect: (cycle: Cycle) => void
  onDateChange: (date: string) => void
}

export default function CycleList({ date, selectedId, onSelect, onDateChange }: Props) {
  const [cycles, setCycles] = useState<Cycle[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetchCycles(date)
      .then(setCycles)
      .catch(() => setCycles([]))
      .finally(() => setLoading(false))
  }, [date])

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1>Scope</h1>
        <input
          type="date"
          value={date}
          onChange={e => onDateChange(e.target.value)}
        />
      </div>
      {loading ? (
        <div className="loading">Loading...</div>
      ) : cycles.length === 0 ? (
        <div className="empty-state">No cycles for this date</div>
      ) : (
        <ul className="cycle-list">
          {cycles.map(c => (
            <CycleListItem
              key={c.id}
              cycle={c}
              selected={c.id === selectedId}
              onClick={() => onSelect(c)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
