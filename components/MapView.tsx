'use client'
import { useState, useEffect } from 'react'
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import '@/lib/leaflet-fix'
import { Destination } from '@/lib/types'

interface Props {
  onSelect: (d: Destination) => void
}

export default function MapView({ onSelect }: Props) {
  const [geoData, setGeoData]           = useState<any>(null)
  const [destinations, setDestinations] = useState<Destination[]>([])
  const [loading, setLoading]           = useState(true)

  useEffect(() => {
    fetch('/data/clusters.geojson')
      .then(r => r.json())
      .then(data => { setGeoData(data); setLoading(false) })
  }, [])

  useEffect(() => {
    fetch('/data/destinations.json')
      .then(r => r.json())
      .then(setDestinations)
  }, [])

  return (
    <div style={{ position: 'relative', height: '100%', width: '100%' }}>
      {loading && (
        <div className="absolute inset-0 z-[2000] flex items-center justify-center bg-white/60">
          <div className="w-10 h-10 border-4 border-green-700 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      <MapContainer center={[54.5, -2.5]} zoom={5} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />

        {/* Cluster polygons — dim background showing forest extent */}
        {geoData && (
          <GeoJSON
            data={geoData}
            style={() => ({
              fillColor: '#2d6a2d',
              fillOpacity: 0.12,
              color: '#2d6a2d',
              weight: 0.8,
              opacity: 0.3,
            })}
          />
        )}

        {/* Destination pins — coloured by Places match status */}
        {destinations.map(dest => {
          const hasPlaces = !!dest.places_data
          return (
            <CircleMarker
              key={`${dest.cluster_id}-${dest.osm_id}`}
              center={[dest.centroid_lat, dest.centroid_lng]}
              radius={6}
              pathOptions={{
                fillColor: hasPlaces ? '#1a5c1a' : '#888',
                fillOpacity: hasPlaces ? 0.85 : 0.5,
                color: '#fff',
                weight: 1.5,
              }}
              eventHandlers={{ click: () => onSelect(dest) }}
            >
              <Tooltip>{dest.name}</Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>
    </div>
  )
}
