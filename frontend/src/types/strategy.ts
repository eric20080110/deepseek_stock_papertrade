export interface ContinuousParam {
  name: string
  type: 'continuous'
  min: number
  max: number
  default: number
  scale: 'linear' | 'logarithmic'
}

export interface IntegerParam {
  name: string
  type: 'integer'
  min: number
  max: number
  step: number
  default: number
}

export interface CategoricalParam {
  name: string
  type: 'categorical'
  options: string[]
  default: string
}

export interface BooleanParam {
  name: string
  type: 'boolean'
  default: boolean
  controls: string[]
}

export type ParamDef = ContinuousParam | IntegerParam | CategoricalParam | BooleanParam

export interface OrderingConstraint {
  type: 'ordering'
  params: string[]
  relation: 'less_than' | 'less_equal'
  repair: 'clamp_upper' | 'clamp_lower' | 'swap'
}

export interface ConditionalConstraint {
  type: 'conditional'
  controller: string
  active_when: boolean
  controlled_params: string[]
}

export interface CategoricalGroupConstraint {
  type: 'categorical_group'
  controller: string
  groups: Record<string, string[]>
  common_params: string[]
}

export type ConstraintDef = OrderingConstraint | ConditionalConstraint | CategoricalGroupConstraint

export interface StrategyConfig {
  config_id: string
  name: string
  description: string
  template_id: string | null
  is_template: boolean
  is_locked: boolean
  locked_by_task_id: string | null
  is_rotation: boolean
  rotation_symbols: string[]
  parameters: ParamDef[]
  constraints: ConstraintDef[]
  created_at: number
  updated_at: number
}
