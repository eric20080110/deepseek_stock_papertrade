import { useEffect, useRef, useState } from 'react'

interface Props {
  taskId: string
}

export function ParamHeatmap({ taskId }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const [individuals, setIndividuals] = useState<any[]>([])
  const [metric, setMetric] = useState('cagr')

  useEffect(() => {
    fetch(`/tasks/${taskId}/individuals?limit=500`)
      .then((r) => r.json())
      .then(setIndividuals)
  }, [taskId])

  const renderHeatmap = () => {
    if (!chartRef.current || individuals.length === 0) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return

    const params = individuals[0]?.params_json ? JSON.parse(individuals[0].params_json) : {}
    const paramNames = Object.keys(params).slice(0, 8)
    if (paramNames.length === 0) return

    const bins = 5
    const data: any[] = []

    for (let i = 0; i < paramNames.length; i++) {
      const name = paramNames[i]
      const vals = individuals.map((ind) => {
        const p = ind.params_json ? JSON.parse(ind.params_json) : {}
        return { val: p[name], metric: ind[metric] || 0 }
      }).filter((v) => v.val !== undefined && !isNaN(Number(v.val)))

      if (vals.length < 3) continue

      const numVals = vals.map((v) => Number(v.val))
      const min = Math.min(...numVals)
      const max = Math.max(...numVals)
      const step = (max - min) / bins || 1
      const binLabels: string[] = []
      const binMetrics: number[] = []
      const binCounts: number[] = []

      for (let b = 0; b < bins; b++) {
        const lo = min + b * step
        const hi = lo + step
        binLabels.push(`${lo.toFixed(2)}-${hi.toFixed(2)}`)
        const inBin = vals.filter((v) => Number(v.val) >= lo && Number(v.val) < hi)
        binCounts.push(inBin.length)
        binMetrics.push(inBin.length > 0 ? inBin.reduce((s, v) => s + v.metric, 0) / inBin.length : 0)
      }

      data.push({
        y: binLabels,
        x: Array(bins).fill(name),
        z: [binMetrics.map((m) => m * (metric === 'cagr' ? 100 : 1))],
        type: 'heatmap',
        text: [binCounts],
        hoverongaps: false,
        showscale: i === 0,
        colorscale: 'RdYlGn',
        colorbar: i === 0 ? { x: 1.02, thickness: 12, title: '' } : undefined,
      })
    }

    if (data.length === 0) return

    const layout = {
      margin: { t: 10, r: 80, b: 80, l: 100 },
      height: 400,
      xaxis: { title: '參數' },
      yaxis: { title: '值區間', automargin: true },
      paper_bgcolor: 'white',
    }

    Plotly.newPlot(chartRef.current, data, layout, { responsive: true, displayModeBar: false })
  }

  useEffect(() => { renderHeatmap() }, [individuals, metric])

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm text-gray-500">顏色依據：</span>
        {['cagr', 'max_drawdown', 'sharpe_ratio'].map((m) => (
          <button key={m} onClick={() => setMetric(m)}
            className={`px-2 py-1 text-xs rounded cursor-pointer ${metric === m ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}>
            {m === 'cagr' ? 'CAGR' : m === 'max_drawdown' ? '回撤' : 'Sharpe'}
          </button>
        ))}
      </div>
      <div ref={chartRef} className="w-full" />
    </div>
  )
}
