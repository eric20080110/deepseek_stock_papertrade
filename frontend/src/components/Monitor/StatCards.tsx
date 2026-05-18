import type { GenerationResult } from '../../types/evolution'

interface Props {
  latest: GenerationResult | null
}

export function StatCards({ latest }: Props) {
  if (!latest) {
    return (
      <div className="grid grid-cols-4 gap-4 mb-4">
        {['帕雷托前沿', '通過門檻', '最高 CAGR', '最低回撤'].map((label) => (
          <div key={label} className="p-4 border rounded-lg bg-white">
            <div className="text-xs text-gray-400">{label}</div>
            <div className="text-xl font-bold text-gray-300 mt-1">--</div>
          </div>
        ))}
      </div>
    )
  }

  const passRate = latest.population_size > 0
    ? ((latest.passed_dynamic / latest.population_size) * 100).toFixed(1)
    : '0'

  return (
    <div className="grid grid-cols-4 gap-4 mb-4">
      <div className="p-4 border rounded-lg bg-white">
        <div className="text-xs text-gray-400">帕雷托前沿</div>
        <div className="text-xl font-bold text-blue-600 mt-1">{latest.pareto_front_size}</div>
      </div>
      <div className="p-4 border rounded-lg bg-white">
        <div className="text-xs text-gray-400">通過門檻</div>
        <div className="text-xl font-bold text-green-600 mt-1">{passRate}%</div>
      </div>
      <div className="p-4 border rounded-lg bg-white">
        <div className="text-xs text-gray-400">最高 CAGR</div>
        <div className="text-xl font-bold text-emerald-600 mt-1">{(latest.best_cagr * 100).toFixed(2)}%</div>
      </div>
      <div className="p-4 border rounded-lg bg-white">
        <div className="text-xs text-gray-400">最低回撤</div>
        <div className="text-xl font-bold text-orange-600 mt-1">{latest.best_drawdown.toFixed(2)}%</div>
      </div>
    </div>
  )
}
