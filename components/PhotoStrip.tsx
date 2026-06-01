'use client'

interface Props {
  osmId: string
  photoCount: number
}

export default function PhotoStrip({ osmId, photoCount }: Props) {
  if (photoCount === 0) return null

  const indices = Array.from({ length: photoCount }, (_, i) => i + 1)

  return (
    <div className="flex gap-2 overflow-x-auto">
      {indices.map(i => (
        <img
          key={i}
          src={`/data/photos/${osmId}/photo_${i}.jpg`}
          alt=""
          className="h-40 w-auto rounded object-cover flex-shrink-0"
          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      ))}
    </div>
  )
}
