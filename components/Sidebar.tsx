'use client'
import { Destination } from '@/lib/types'
import ForestPanel from './ForestPanel'

interface Props {
  destination: Destination | null
  onClose: () => void
}

export default function Sidebar({ destination, onClose }: Props) {
  return (
    <aside className="w-full sm:w-[400px] bg-white border-l border-gray-200 flex flex-col overflow-y-auto">
      {!destination ? (
        <div className="flex items-center justify-center h-full text-gray-400 p-8 text-center">
          Click a forest on the map to explore it.
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between p-4 border-b border-gray-100 sticky top-0 bg-white z-10">
            <h2 className="font-semibold text-lg leading-tight truncate pr-2">
              {destination.places_data?.canonical_name ?? destination.name}
            </h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 flex-shrink-0">✕</button>
          </div>
          <ForestPanel destination={destination} />
        </>
      )}
    </aside>
  )
}
