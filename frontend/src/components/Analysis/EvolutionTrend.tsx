import { useEffect, useRef } from 'react'

interface Props {
  taskId: string
}

export function EvolutionTrend({ taskId }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartRef.current) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return

    fetch(`/tasks/${taskId}/charts/evolution-trend`)
      .then((r) => r.json())
      .then((points: any[]) => {
        if (points.length === 0) return
        const gens = points.map((p) => p.generation)
        const cagr = points.map((p) => p.best_cagr * 100)
        const dd = points.map((p) => p.best_drawdown)
        const sharpe = points.map((p) => p.best_sharpe)
        const passRate = points.map((p) =>
          p.population_size > 0 ? (p.passed_dynamic / p.population_size) * 100 : 0
        )

        const data = [
          { x: gens, y: cagr, type: 'scatter', mode: 'lines+markers', name: '最高 CAGR %', line: { color: '#059669' } },
          { x: gens, y: dd, type: 'scatter', mode: 'lines+markers', name: '最低回撤 %', yaxis: 'y2', line: { color: '#dc2626' } },
          { x: gens, y: sharpe, type: 'scatter', mode: 'lines+markers', name: '最高 Sharpe', yaxis: 'y3', line: { color: '#2563eb' } },
          { x: gens, y: passRate, type: 'scatter', mode: 'lines', name: '通過率 %', line: { color: '#d1d5db', dash: 'dot' } },
        ]

        const layout: any = {
          margin: { t: 20, r: 60, b: 40, l: 60 },
          height: 400,
          showlegend: true,
          xaxis: { title: '世代' },
          yaxis: { title: 'CAGR / 回撤 %', side: 'left' },
          yaxis2: { overlaying: 'y', side: 'left', showgrid: false },
          yaxis3: { title: 'Sharpe', side: 'right', overlaying: 'y', showgrid: false },
          paper_bgcolor: 'white', plot_bgcolor: 'white',
        }

        Plotly.newPlot(chartRef.current, data, layout, { responsive: true, displayModeBar: false })
      })
  }, [taskId])

  return <div ref={chartRef} className="w-full" />
}
