'use client'
import dynamic from 'next/dynamic'
import { useState } from 'react'
import Sidebar from '@/components/Sidebar'
import { ForestCluster } from '@/lib/types'

const MapView = dynamic(() => import('@/components/MapView'), { ssr: false })

export default function Home() {
  const [selected, setSelected] = useState<ForestCluster | null>(null)

  return (
    <main className="flex flex-col sm:flex-row h-screen w-screen">
      <div className="flex-1 min-h-[60vh] sm:min-h-0">
        <MapView onSelect={setSelected} />
      </div>
      <Sidebar forest={selected} onClose={() => setSelected(null)} />
    </main>
  )
}
