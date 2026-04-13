import { useState, useEffect } from 'react'
import type { Cycle } from './api/types'
import { fetchCycles } from './api/client'
import CycleList from './components/CycleList'
import CycleInspector from './components/CycleInspector'
import LearningDashboard from './components/LearningDashboard'

type View = 'inspector' | 'learning'

function todayString(): string {
  const d = new Date()
  return d.toISOString().slice(0, 10)
}

export default function App() {
  const [view, setView] = useState<View>('inspector')
  const [date, setDate] = useState(todayString)
  const [selectedCycle, setSelectedCycle] = useState<Cycle | null>(null)
  const [cycles, setCyclesForNav] = useState<Cycle[]>([])

  function handleSelect(cycle: Cycle) {
    setSelectedCycle(cycle)
  }

  function handleDateChange(newDate: string) {
    setDate(newDate)
    setSelectedCycle(null)
  }

  // Navigation: find prev/next cycle in the list
  const currentIndex = selectedCycle
    ? cycles.findIndex(c => c.id === selectedCycle.id)
    : -1

  const canPrev = currentIndex > 0
  const canNext = currentIndex >= 0 && currentIndex < cycles.length - 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* Nav bar */}
      <nav className="scope-nav">
        <button
          className={`scope-nav-tab ${view === 'inspector' ? 'active' : ''}`}
          onClick={() => setView('inspector')}
        >
          Cycle Inspector
        </button>
        <button
          className={`scope-nav-tab ${view === 'learning' ? 'active' : ''}`}
          onClick={() => setView('learning')}
        >
          Learning Curves
        </button>
      </nav>

      <div className="app-layout" style={{ flex: 1 }}>
        {view === 'inspector' ? (
          <>
            <CycleListWithNav
              date={date}
              selectedId={selectedCycle?.id ?? null}
              onSelect={handleSelect}
              onDateChange={handleDateChange}
              onCyclesLoaded={setCyclesForNav}
            />
            {selectedCycle ? (
              <CycleInspector
                cycleId={selectedCycle.id}
                onPrev={canPrev ? () => setSelectedCycle(cycles[currentIndex - 1]) : null}
                onNext={canNext ? () => setSelectedCycle(cycles[currentIndex + 1]) : null}
              />
            ) : (
              <div className="main-panel">
                <div className="empty-state">Select a cycle to inspect</div>
              </div>
            )}
          </>
        ) : (
          <LearningDashboard />
        )}
      </div>
    </div>
  )
}

// Wrapper to expose cycles for navigation
function CycleListWithNav({
  date, selectedId, onSelect, onDateChange, onCyclesLoaded
}: {
  date: string
  selectedId: number | null
  onSelect: (cycle: Cycle) => void
  onDateChange: (date: string) => void
  onCyclesLoaded: (cycles: Cycle[]) => void
}) {
  useEffect(() => {
    fetchCycles(date)
      .then(onCyclesLoaded)
      .catch(() => onCyclesLoaded([]))
  }, [date, onCyclesLoaded])

  return (
    <CycleList
      date={date}
      selectedId={selectedId}
      onSelect={onSelect}
      onDateChange={onDateChange}
    />
  )
}
