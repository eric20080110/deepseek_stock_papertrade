import { useEffect, useRef } from 'react'
import type { GenerationResult } from '../../types/evolution'

declare global {
  interface Window { Plotly: any }
}

interface Props {
  history: GenerationResult[]
}

export function TrendChart({ history }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartRef.current || history.length === 0) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return

    const gens = history.map((g) => g.generation)
    const cagr = history.map((g) => g.best_cagr * 100)
    const dd = history.map((g) => g.best_drawdown)
    const sharpe = history.map((g) => g.best_sharpe)
    const passRate = history.map((g) =>
      g.population_size > 0 ? (g.passed_dynamic / g.population_size) * 100 : 0
    )

    const data = [
      { x: gens, y: cagr, type: 'scatter', mode: 'lines+markers', name: '最高 CAGR %', line: { color: '#059669' } },
      { x: gens, y: dd, type: 'scatter', mode: 'lines+markers', name: '最低回撤 %', yaxis: 'y2', line: { color: '#dc2626' } },
      { x: gens, y: sharpe, type: 'scatter', mode: 'lines+markers', name: '最高 Sharpe', yaxis: 'y3', line: { color: '#2563eb' } },
      { x: gens, y: passRate, type: 'scatter', mode: 'lines', name: '通過率 %', line: { color: '#d1d5db', dash: 'dot' }, fill: 'tozeroy' },
    ]

    const layout: any = {
      margin: { t: 20, r: 60, b: 40, l: 60 },
      height: 300,
      showlegend: true,
      legend: { orientation: 'h', y: 1.1 },
      xaxis: { title: '世代', domain: [0, 0.9] },
      yaxis: { title: 'CAGR / 回撤 %', side: 'left' },
      yaxis2: { overlaying: 'y', side: 'left', showgrid: false },
      yaxis3: { title: 'Sharpe', side: 'right', overlaying: 'y', showgrid: false },
      paper_bgcolor: 'white', plot_bgcolor: 'white',
    }

    Plotly.newPlot(chartRef.current, data, layout, { responsive: true, displayModeBar: false })
  }, [history])

  return <div ref={chartRef} className="w-full" />
}
