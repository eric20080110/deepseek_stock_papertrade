import type { GenerationResult } from '../../types/evolution'

const TIPS: Record<string, string> = {
  '帕雷托前沿': '本代在 CAGR、夏普率、最大回撤三個目標上無法被任何個體同時超越的最優解集合',
  '通過門檻': '同時通過動態適應門檻（相對於族群表現）的個體佔比',
  '最高 CAGR': '複合年化報酬率（Compound Annual Growth Rate）：衡量策略年均增長速度',
  '最低回撤': '本代最優個體的最大資金回撤幅度，數值越小越好',
}

function Card({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="p-4 border rounded-lg bg-white" title={TIPS[label]}>
      <div className="text-xs text-gray-400 flex items-center gap-1">
        {label}
        <span className="text-gray-300 cursor-help" title={TIPS[label]}>?</span>
      </div>
      <div className={`text-xl font-bold mt-1 ${color}`}>{value}</div>
    </div>
  )
}

interface Props {
  latest: GenerationResult | null
}

export function StatCards({ latest }: Props) {
  if (!latest) {
    return (
      <div className="grid grid-cols-4 gap-4 mb-4">
        {Object.keys(TIPS).map((label) => (
          <div key={label} className="p-4 border rounded-lg bg-white" title={TIPS[label]}>
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
      <Card label="帕雷托前沿" value={String(latest.pareto_front_size)} color="text-blue-600" />
      <Card label="通過門檻" value={`${passRate}%`} color="text-green-600" />
      <Card label="最高 CAGR" value={`${(latest.best_cagr * 100).toFixed(2)}%`} color="text-emerald-600" />
      <Card label="最低回撤" value={`${latest.best_drawdown.toFixed(2)}%`} color="text-orange-600" />
    </div>
  )
}
