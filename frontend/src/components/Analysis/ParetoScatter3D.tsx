import { useEffect, useRef } from 'react'
import { useTaskStore } from '../../store/taskStore'

interface Props {
  taskId: string
}

export function ParetoScatter3D({ taskId }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const setSelectedIndividualId = useTaskStore((s) => s.setSelectedIndividualId)

  useEffect(() => {
    if (!chartRef.current) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return

    fetch(`/tasks/${taskId}/charts/pareto-scatter`)
      .then((r) => r.json())
      .then((all: any[]) => {
        if (all.length === 0) return
        const el = chartRef.current
        if (!el) return
        const front = all.filter((p) => p.pareto_rank === 1)
        const dominated = all.filter((p) => p.pareto_rank !== 1)

        const traces = []
        if (dominated.length > 0) {
          traces.push({
            x: dominated.map((p) => p.cagr * 100),
            y: dominated.map((p) => p.dd),
            z: dominated.map((p) => p.sharpe),
            customdata: dominated.map((p) => p.id),
            text: dominated.map((p) =>
              `Gen ${p.generation}<br>ID: ${p.id.substring(0, 8)}<br>CAGR: ${(p.cagr * 100).toFixed(2)}%<br>DD: ${p.dd.toFixed(2)}%<br>Sharpe: ${p.sharpe.toFixed(2)}<br>Rank: ${p.pareto_rank ?? '-'}`
            ),
            mode: 'markers',
            type: 'scatter3d',
            name: '被支配',
            marker: { size: 3, color: '#9ca3af', opacity: 0.5 },
            hoverinfo: 'text',
          })
        }
        if (front.length > 0) {
          traces.push({
            x: front.map((p) => p.cagr * 100),
            y: front.map((p) => p.dd),
            z: front.map((p) => p.sharpe),
            customdata: front.map((p) => p.id),
            text: front.map((p) =>
              `Gen ${p.generation}<br>ID: ${p.id.substring(0, 8)}<br>CAGR: ${(p.cagr * 100).toFixed(2)}%<br>DD: ${p.dd.toFixed(2)}%<br>Sharpe: ${p.sharpe.toFixed(2)}<br>OOS: ${p.oos.toFixed(3)}`
            ),
            mode: 'markers',
            type: 'scatter3d',
            name: '帕雷托前緣',
            marker: {
              size: 6,
              color: front.map((p) => p.oos),
              colorscale: 'RdYlGn',
              showscale: true,
              colorbar: { title: 'OOS', thickness: 10 },
            },
            hoverinfo: 'text',
          })
        }

        const layout = {
          margin: { t: 10, r: 10, b: 40, l: 50 },
          height: 500,
          scene: {
            xaxis: { title: 'CAGR %' },
            yaxis: { title: '最大回撤 %', autorange: 'reversed' },
            zaxis: { title: 'Sharpe' },
          },
          paper_bgcolor: 'white',
        }

        Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false })

        el.on('plotly_click', (eventData: any) => {
          const pt = eventData?.points?.[0]
          if (!pt) return
          const id = pt.customdata
          if (id) setSelectedIndividualId(id)
        })
      })
  }, [taskId])

  return <div ref={chartRef} className="w-full" />
}
