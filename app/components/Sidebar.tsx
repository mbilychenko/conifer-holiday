'use client'
import { ForestCluster } from '@/lib/types'
import ForestPanel from './ForestPanel'

interface Props {
  forest: ForestCluster | null
  onClose: () => void
}

export default function Sidebar({ forest, onClose }: Props) {
  return (
    <aside className="w-full sm:w-[380px] bg-white border-l border-gray-200 flex flex-col overflow-y-auto">
      {!forest ? (
        <div className="flex items-center justify-center h-full text-gray-400 p-8 text-center">
          Click a forest on the map to explore it.
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between p-4 border-b">
            <h2 className="font-semibold text-lg truncate">{forest.name}</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 ml-2">✕</button>
          </div>
          <ForestPanel forest={forest} />
        </>
      )}
    </aside>
  )
}
