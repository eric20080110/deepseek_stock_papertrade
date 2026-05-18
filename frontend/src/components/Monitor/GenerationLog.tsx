import type { GenerationResult } from '../../types/evolution'

interface Props {
  history: GenerationResult[]
}

export function GenerationLog({ history }: Props) {
  const recent = [...history].reverse().slice(0, 100)

  return (
    <div className="border rounded-lg bg-white max-h-48 overflow-y-auto">
      {recent.length === 0 && <div className="p-3 text-xs text-gray-400 text-center">等待第一代完成...</div>}
      {recent.map((g) => {
        const ids = g.pareto_front.map((p) => p.id.slice(0, 8))
        return (
          <div key={g.generation} className="px-3 py-1.5 border-b last:border-0 text-xs text-gray-600 hover:bg-gray-50">
            第 {g.generation} 代 ｜ 前沿 {g.pareto_front_size} 個 ｜
            最高 CAGR {(g.best_cagr * 100).toFixed(2)}% ｜
            最低回撤 {g.best_drawdown.toFixed(2)}% ｜
            編號 {ids.join(', ') || '-'} ｜
            耗時 {g.duration_sec.toFixed(1)}s
          </div>
        )
      })}
    </div>
  )
}
