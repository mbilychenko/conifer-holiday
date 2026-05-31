'use client'

const TYPES = ['All', 'Conifer', 'Mixed mainly conifer'] as const

interface Props {
  active: string
  onChange: (t: string) => void
}

export default function FilterBar({ active, onChange }: Props) {
  return (
    <div className="absolute top-3 left-3 z-[1000] flex gap-2">
      {TYPES.map(t => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`px-3 py-1 rounded-full text-sm font-medium shadow
            ${active === t ? 'bg-green-700 text-white' : 'bg-white text-gray-700 border border-gray-300'}`}
        >
          {t === 'Mixed mainly conifer' ? 'Mixed' : t}
        </button>
      ))}
    </div>
  )
}
