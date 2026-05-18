import { useEffect, useRef } from 'react'
import { useTaskStore } from '../../store/taskStore'
import type { GenerationResult } from '../../types/evolution'

interface Props {
  latest: GenerationResult | null
}

export function LiveScatter({ latest }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const setSelectedIndividualId = useTaskStore((s) => s.setSelectedIndividualId)

  useEffect(() => {
    if (!chartRef.current || !latest || latest.pareto_front.length === 0) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return

    const front = latest.pareto_front
    const data = [{
      x: front.map((f) => f.cagr * 100),
      y: front.map((f) => f.dd),
      customdata: front.map((f) => f.id),
      text: front.map((f) => `CAGR:${(f.cagr * 100).toFixed(2)}% DD:${f.dd.toFixed(2)}% Sharpe:${f.sharpe.toFixed(2)}`),
      mode: 'markers',
      type: 'scatter',
      marker: {
        size: front.map((f) => Math.max(8, f.sharpe * 8)),
        color: front.map((f) => f.oos),
        colorscale: 'RdYlGn',
        showscale: true,
        colorbar: { title: 'OOS', thickness: 10, len: 0.5 },
      },
      hoverinfo: 'text',
    }]

    const layout = {
      margin: { t: 10, r: 20, b: 40, l: 50 },
      height: 350,
      xaxis: { title: 'CAGR %' },
      yaxis: { title: '最大回撤 %', autorange: 'reversed' },
      paper_bgcolor: 'white', plot_bgcolor: 'white',
    }

    const el = chartRef.current
    Plotly.newPlot(el, data, layout, { responsive: true, displayModeBar: false })
    el.on('plotly_click', (eventData: any) => {
      const pt = eventData?.points?.[0]
      if (!pt) return
      const id = pt.customdata
      if (id) setSelectedIndividualId(id)
    })
  }, [latest])

  return <div ref={chartRef} className="w-full" />
}
