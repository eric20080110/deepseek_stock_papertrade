interface Props {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

const sizes = { sm: 'h-4 w-4', md: 'h-6 w-6', lg: 'h-8 w-8' }

export function LoadingSpinner({ size = 'md', label }: Props) {
  return (
    <div className="flex items-center gap-2 text-gray-400">
      <svg className={`animate-spin ${sizes[size]}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      {label && <span className="text-sm">{label}</span>}
    </div>
  )
}

export function PageLoading({ label = '載入中...' }: { label?: string }) {
  return (
    <div className="relative">
      <div className="absolute top-0 left-0 right-0 h-0.5 bg-gray-100 overflow-hidden">
        <div className="h-full bg-blue-500 animate-[slide_1.2s_ease-in-out_infinite]"
          style={{ width: '40%', animation: 'pageload 1.2s ease-in-out infinite' }} />
      </div>
      <style>{`@keyframes pageload { 0%{transform:translateX(-100%)} 100%{transform:translateX(350%)} }`}</style>
      <div className="p-8 text-center text-sm text-gray-400">{label}</div>
    </div>
  )
}
