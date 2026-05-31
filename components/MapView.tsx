'use client'
import { useState, useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import '@/lib/leaflet-fix'
import { typeToColour } from '@/lib/forestUtils'
import { ForestCluster } from '@/lib/types'
import FilterBar from './FilterBar'

interface Props {
  onSelect: (f: ForestCluster) => void
}

export default function MapView({ onSelect }: Props) {
  const [geoData, setGeoData] = useState<any>(null)
  const [clusters, setClusters] = useState<ForestCluster[]>([])
  const [filterType, setFilterType] = useState('All')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/data/clusters.geojson')
      .then(r => r.json())
      .then(data => { setGeoData(data); setLoading(false) })
  }, [])

  useEffect(() => {
    fetch('/data/clusters_meta.json')
      .then(r => r.json())
      .then(setClusters)
  }, [])

  const filteredGeo = useMemo(() => {
    if (!geoData) return null
    if (filterType === 'All') return geoData
    return {
      ...geoData,
      features: geoData.features.filter(
        (f: any) => f.properties?.dominant_type === filterType
      ),
    }
  }, [geoData, filterType])

  const filteredClusters = useMemo(() => {
    if (filterType === 'All') return clusters
    return clusters.filter(c => c.dominant_type === filterType)
  }, [clusters, filterType])

  return (
    <div style={{ position: 'relative', height: '100%', width: '100%' }}>
      {loading && (
        <div className="absolute inset-0 z-[2000] flex items-center justify-center bg-white/60">
          <div className="w-10 h-10 border-4 border-green-700 border-t-transparent rounded-full animate-spin" />
        </div>
      )}
      <FilterBar active={filterType} onChange={setFilterType} />
      <MapContainer
        center={[54.5, -2.5]}
        zoom={5}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {filteredGeo && (
          <GeoJSON
            key={filterType}
            data={filteredGeo}
            style={(feature) => ({
              fillColor: typeToColour(feature?.properties?.dominant_type ?? ''),
              fillOpacity: 0.5,
              color: '#fff',
              weight: 0.5,
            })}
          />
        )}
        {filteredClusters.map(forest => (
          <CircleMarker
            key={forest.id}
            center={[forest.lat, forest.lng]}
            radius={8}
            pathOptions={{
              fillColor: typeToColour(forest.dominant_type),
              fillOpacity: 0.9,
              color: '#fff',
              weight: 1.5,
            }}
            eventHandlers={{ click: () => onSelect(forest) }}
          >
            <Tooltip>{forest.name}</Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
