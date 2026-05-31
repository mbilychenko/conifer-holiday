import { ForestCluster } from '@/lib/types'
import { typeToColour, typeToLabel } from '@/lib/forestUtils'

export default function ForestPanel({ forest }: { forest: ForestCluster }) {
  return (
    <div className="p-4 space-y-3">
      <span
        className="inline-block px-2 py-1 rounded text-white text-sm"
        style={{ backgroundColor: typeToColour(forest.dominant_type) }}
      >
        {typeToLabel(forest.dominant_type)}
      </span>
      <div className="text-sm text-gray-600 space-y-1">
        <p><span className="font-medium">Country:</span> {forest.country}</p>
        <p><span className="font-medium">Area:</span> {forest.hectares.toLocaleString()} ha</p>
        <p><span className="font-medium">NFI polygons:</span> {forest.polygon_count}</p>
      </div>
    </div>
  )
}
