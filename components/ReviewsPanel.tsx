'use client'
import { PlacesData } from '@/lib/types'

function Stars({ rating }: { rating: number }) {
  const full  = Math.floor(rating)
  const half  = rating % 1 >= 0.5 ? 1 : 0
  const empty = 5 - full - half
  return (
    <span className="text-yellow-400 text-sm">
      {'★'.repeat(full)}{'½'.repeat(half)}{'☆'.repeat(empty)}
    </span>
  )
}

export default function ReviewsPanel({ data }: { data: PlacesData }) {
  return (
    <div className="space-y-3">
      {/* Rating summary */}
      {data.rating != null && (
        <div className="flex items-center gap-2">
          <Stars rating={data.rating} />
          <span className="font-semibold text-sm">{data.rating.toFixed(1)}</span>
          {data.review_count != null && (
            <span className="text-gray-400 text-sm">({data.review_count.toLocaleString()} reviews)</span>
          )}
          {data.google_maps_uri && (
            <a
              href={data.google_maps_uri}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto text-xs text-green-700 hover:underline whitespace-nowrap"
            >
              View on Google Maps →
            </a>
          )}
        </div>
      )}

      {/* Review excerpts */}
      {data.reviews.length > 0 && (
        <div className="space-y-2">
          {data.reviews.map((rv, i) => (
            <div key={i} className="bg-gray-50 rounded p-2 text-xs text-gray-700 space-y-0.5">
              <div className="flex items-center gap-1.5">
                <span className="font-medium text-gray-800">{rv.author}</span>
                {rv.rating != null && <span className="text-yellow-400">{'★'.repeat(rv.rating)}</span>}
                <span className="text-gray-400 ml-auto">{rv.relative_time}</span>
              </div>
              <p className="leading-relaxed line-clamp-3">{rv.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
