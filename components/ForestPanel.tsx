import { Destination } from '@/lib/types'
import PhotoStrip from './PhotoStrip'
import ReviewsPanel from './ReviewsPanel'

export default function ForestPanel({ destination: d }: { destination: Destination }) {
  const pd = d.places_data

  return (
    <div className="p-4 space-y-4">
      {/* Photos */}
      {pd?.photo_paths && pd.photo_paths.length > 0 && (
        <PhotoStrip osmId={d.osm_id} photoCount={pd.photo_paths.length} />
      )}

      {/* Meta */}
      <div className="text-sm text-gray-600 space-y-1">
        {pd?.editorial_summary && (
          <p className="text-gray-700 italic">{pd.editorial_summary}</p>
        )}
        <p><span className="font-medium">Area:</span> {d.area_ha.toLocaleString()} ha</p>
        <p><span className="font-medium">Zone:</span> {d.cluster_name}</p>
        {pd?.address && (
          <p><span className="font-medium">Address:</span> {pd.address}</p>
        )}
        {pd?.website && (
          <a
            href={pd.website}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-green-700 hover:underline truncate"
          >
            {pd.website.replace(/^https?:\/\//, '')}
          </a>
        )}
      </div>

      {/* Opening hours */}
      {pd?.opening_hours && pd.opening_hours.length > 0 && (
        <details className="text-xs text-gray-500">
          <summary className="cursor-pointer font-medium text-gray-600 hover:text-gray-800">
            Opening hours
          </summary>
          <ul className="mt-1 space-y-0.5 pl-2">
            {pd.opening_hours.map((h, i) => <li key={i}>{h}</li>)}
          </ul>
        </details>
      )}

      {/* Reviews */}
      {pd ? (
        <ReviewsPanel data={pd} />
      ) : (
        <p className="text-xs text-gray-400 italic">
          No visitor information found for this forest.
        </p>
      )}
    </div>
  )
}
