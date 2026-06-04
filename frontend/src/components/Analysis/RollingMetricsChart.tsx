import { useEffect, useRef } from 'react'

interface Props {
  taskId: string
  sid: string
}

export function RollingMetricsChart({ taskId, sid }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartRef.current) return
    const Plotly = (window as unknown as Record<string, unknown>).Plotly as {
      newPlot: (el: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config: Record<string, unknown>) => void
    } | undefined
    if (!Plotly) return

    fetch(`/tasks/${taskId}/individuals/${sid}/rolling-metrics?window=60`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.labels?.length || !chartRef.current) return
        const traces: Record<string, unknown>[] = [
          { x: data.labels, y: data.rolling_sharpe, type: 'scatter', mode: 'lines', name: '滾動 Sharpe', yaxis: 'y', line: { color: '#2563eb' } },
          { x: data.labels, y: data.rolling_volatility, type: 'scatter', mode: 'lines', name: '滾動波動率 %', yaxis: 'y2', line: { color: '#dc2626' } },
          { x: data.labels, y: data.rolling_win_rate, type: 'scatter', mode: 'lines', name: '滾動勝率 %', yaxis: 'y3', line: { color: '#16a34a', dash: 'dot' } },
        ]
        const layout: Record<string, unknown> = {
          title: { text: '滾動指標 (60 bars)' },
          margin: { t: 40, r: 60, b: 40, l: 60 }, height: 250,
          xaxis: { title: 'Bar' },
          yaxis: { title: 'Sharpe', side: 'left' },
          yaxis2: { title: '波動率 %', overlaying: 'y', side: 'right', showgrid: false },
          yaxis3: { title: '勝率 %', overlaying: 'y', side: 'right', showgrid: false, position: 0.95 },
          paper_bgcolor: 'white', plot_bgcolor: 'white',
          legend: { x: 1, xanchor: 'right', y: 0, yanchor: 'bottom', font: { size: 9 } },
        }
        Plotly.newPlot(chartRef.current, traces, layout, { responsive: true, displayModeBar: false })
      })
  }, [taskId, sid])

  return <div ref={chartRef} className="w-full" />
}
