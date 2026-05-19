import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import type { ParamDef, ConstraintDef } from '../../types/strategy'
import { BasicInfoStep } from './BasicInfoStep'
import { ParamSpaceEditor } from './ParamSpaceEditor'

interface Props {
  templateId: string | null
  configId?: string
  onSave: () => void
  onCancel: () => void
}

export function StrategyForm({ templateId, configId, onSave, onCancel }: Props) {
  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [templateName, setTemplateName] = useState('')
  const [params, setParams] = useState<ParamDef[]>([])
  const [constraints, setConstraints] = useState<ConstraintDef[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (configId) {
      api.getStrategy(configId).then((s) => {
        setName(s.name)
        setDescription(s.description)
        setParams(s.parameters)
        setConstraints(s.constraints)
      })
    }
  }, [configId])

  useEffect(() => {
    if (templateId) {
      api.listTemplates().then((templates) => {
        const t = templates.find((t) => t.template_id === templateId)
        if (t) {
          setTemplateName(t.name)
          if (!configId) {
            setParams(t.parameters)
            setConstraints(t.constraints)
          }
        }
      })
    }
  }, [templateId, configId])

  const validate = (): boolean => {
    const errs: Record<string, string> = {}
    if (!name.trim()) errs.name = '策略名稱不可為空'
    if (name.length > 50) errs.name = '策略名稱最多 50 字'

    const names = params.map((p) => p.name)
    if (new Set(names).size !== names.length) errs.dup = '參數名稱不可重複'
    for (const n of names) {
      if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(n)) errs[`name_${n}`] = `參數名稱「${n}」只允許英文、數字與底線，且不可數字開頭`
    }

    for (const c of constraints) {
      if (c.type === 'ordering') {
        for (const p of c.params) {
          if (!names.includes(p)) errs[`constraint_ref_${p}`] = `約束引用不存在參數「${p}」`
        }
      }
      if (c.type === 'conditional') {
        if (!names.includes(c.controller)) errs[`cond_controller_${c.controller}`] = `條件控制器「${c.controller}」不存在`
        for (const cp of c.controlled_params) {
          if (!names.includes(cp)) errs[`cond_param_${cp}`] = `受控參數「${cp}」不存在`
        }
      }
      if (c.type === 'categorical_group') {
        if (!names.includes(c.controller)) errs[`cat_controller_${c.controller}`] = `群組控制器「${c.controller}」不存在`
        const catParam = params.find((p) => p.name === c.controller)
        if (catParam && catParam.type === 'categorical' && 'options' in catParam) {
          for (const opt of (catParam as any).options) {
            if (c.groups[opt]) {
              for (const gp of c.groups[opt]) {
                if (!names.includes(gp)) errs[`cat_group_param_${gp}`] = `群組參數「${gp}」不存在`
              }
            }
          }
        }
      }
    }

    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSave = async () => {
    if (!validate()) return
    setSaving(true)
    try {
      if (configId) {
        await api.updateStrategy(configId, { name, description, parameters: params, constraints })
      } else if (templateId) {
        await api.createStrategy({ template_id: templateId, name, description, parameters: params, constraints })
      }
      onSave()
    } catch (e: any) {
      toast.error(e.message)
    }
    setSaving(false)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{configId ? '編輯策略' : '建立策略'}</h1>
        <button onClick={onCancel} className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50 cursor-pointer">
          取消
        </button>
      </div>

      <div className="flex items-center gap-2 mb-6">
        <span className={`px-3 py-1 text-sm rounded-full ${step === 1 ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}>1. 基本資訊</span>
        <div className="w-8 h-px bg-gray-300" />
        <span className={`px-3 py-1 text-sm rounded-full ${step === 2 ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}>2. 參數設定</span>
      </div>

      {step === 1 && (
        <div className="max-w-lg">
          <BasicInfoStep name={name} description={description} templateName={templateName} onChange={(d) => { setName(d.name); setDescription(d.description) }} />
          {errors.name && <p className="text-red-500 text-xs mt-1">{errors.name}</p>}
          <div className="mt-6">
            <button onClick={() => setStep(2)} disabled={!name.trim()} className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 cursor-pointer">
              下一步
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div>
          <ParamSpaceEditor params={params} constraints={constraints} onParamsChange={setParams} onConstraintsChange={setConstraints} errors={errors} />
          <div className="flex items-center gap-3 mt-6">
            <button onClick={() => setStep(1)} className="px-6 py-2 border rounded-lg hover:bg-gray-50 cursor-pointer">
              上一步
            </button>
            <button onClick={handleSave} disabled={saving} className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 cursor-pointer">
              {saving ? '儲存中...' : configId ? '更新策略' : '建立策略'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
