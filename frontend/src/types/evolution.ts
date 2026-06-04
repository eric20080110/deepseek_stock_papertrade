export interface TaskConfig {
  strategy_config_id: string
  symbols: string[]
  start_date: string
  end_date: string
  timeframe: string
  population_size: number | null
  max_generations: number | null
  crossover_rate: number | null
  mutation_rate: number | null
  parent_pool_ratio: number
  early_stop_generations: number | null
}

export interface EvolutionTask {
  task_id: string
  name?: string | null
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  created_at: number
  started_at: number | null
  completed_at: number | null
  config: TaskConfig
  current_generation: number
  total_generations: number
  progress_pct: number
  error_message: string | null
  result_summary: Record<string, unknown> | null
}

export interface GenerationResult {
  generation: number
  total_generations: number
  duration_sec: number
  population_size: number
  passed_absolute: number
  passed_dynamic: number
  pareto_front_size: number
  pareto_front: FrontIndividual[]
  best_cagr: number
  best_sharpe: number
  best_drawdown: number
  crossover_count: number
  mutation_count: number
  repair_count: number
  resample_count: number
  dynamic_thresholds: Record<string, number>
}

export interface FrontIndividual {
  id: string
  cagr: number
  dd: number
  sharpe: number
  oos: number
  sortino?: number
  calmar?: number
  profit_factor?: number
  win_rate?: number
  var_95?: number
  cvar_95?: number
}

export type ViewType = 'dashboard' | 'strategy' | 'new-task' | 'queue' | 'monitor' | 'analysis' | 'gene-pool' | 'paper-trading' | 'live-trading'
