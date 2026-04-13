import { useEffect, useState } from 'react'
import type { CorrectionRatePoint, CalibrationData, TaskAccuracy } from '../api/types'
import { fetchCorrectionRate, fetchConfidenceCalibration, fetchPerTaskAccuracy } from '../api/client'
import CorrectionRateChart from './CorrectionRateChart'
import CalibrationChart from './CalibrationChart'
import TaskAccuracyChart from './TaskAccuracyChart'
import FewShotImpactCard from './FewShotImpactCard'

type Range = 7 | 30 | 365

export default function LearningDashboard() {
  const [range, setRange] = useState<Range>(30)
  const [rateData, setRateData] = useState<CorrectionRatePoint[]>([])
  const [calibration, setCalibration] = useState<CalibrationData | null>(null)
  const [taskAccuracy, setTaskAccuracy] = useState<TaskAccuracy[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchCorrectionRate(range).catch(() => []),
      fetchConfidenceCalibration().catch(() => null),
      fetchPerTaskAccuracy().catch(() => []),
    ]).then(([rate, cal, tasks]) => {
      setRateData(rate)
      setCalibration(cal)
      setTaskAccuracy(tasks)
      setLoading(false)
    })
  }, [range])

  // Check if there's enough data
  const totalCycles = rateData.reduce((s, d) => s + d.total_cycles, 0)
  const totalCorrections = rateData.reduce((s, d) => s + d.corrections, 0)
  const insufficientData = totalCycles < 10 || totalCorrections < 3

  if (loading) {
    return <div className="main-panel"><div className="loading">Loading learning data...</div></div>
  }

  return (
    <div className="main-panel">
      <div className="inspector-header">
        <h2>Learning Curves</h2>
        <div className="nav-buttons">
          {([7, 30, 365] as Range[]).map(r => (
            <button
              key={r}
              onClick={() => setRange(r)}
              style={r === range ? { background: 'var(--color-accent)', color: 'white', borderColor: 'var(--color-accent)' } : {}}
            >
              {r === 365 ? 'All' : `${r}d`}
            </button>
          ))}
        </div>
      </div>

      {insufficientData && (
        <div style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)',
          padding: 16,
          marginBottom: 16,
          color: 'var(--color-text-muted)',
          fontSize: 13,
        }}>
          Insufficient data for meaningful charts ({totalCycles} cycles, {totalCorrections} corrections).
          Run Pulse and make corrections to build up the dataset.
        </div>
      )}

      {/* Correction Rate */}
      <div className="section">
        <div className="section-header">Correction Rate Over Time</div>
        <div className="section-body">
          <CorrectionRateChart data={rateData} />
        </div>
      </div>

      {/* Confidence Calibration */}
      {calibration && (
        <div className="section">
          <div className="section-header">Confidence Calibration</div>
          <div className="section-body">
            <CalibrationChart data={calibration} />
          </div>
        </div>
      )}

      {/* Per-Task Accuracy */}
      <div className="section">
        <div className="section-header">Per-Task Accuracy</div>
        <div className="section-body">
          <TaskAccuracyChart data={taskAccuracy} />
        </div>
      </div>

      {/* Few-Shot Impact */}
      <div className="section">
        <div className="section-header">Few-Shot Impact</div>
        <div className="section-body">
          <FewShotImpactCard />
        </div>
      </div>
    </div>
  )
}
