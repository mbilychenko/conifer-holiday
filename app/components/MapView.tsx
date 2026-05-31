'use client'
import { useState, useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import '@/lib/leaflet-fix'
import { typeToColour, clusterToColour } from '@/lib/forestUtils'
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
  const [colorMode, setColorMode] = useState<'type' | 'cluster'>('type')
  const [hiddenClusters, setHiddenClusters] = useState<Set<string>>(new Set())

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

  // Stable color map: cluster id -> color, based on sorted-by-id index
  const clusterColorMap = useMemo(() => {
    const sorted = [...clusters].sort((a, b) => a.id.localeCompare(b.id))
    const map = new Map<string, string>()
    sorted.forEach((c, i) => map.set(c.id, clusterToColour(i)))
    return map
  }, [clusters])

  const filteredGeo = useMemo(() => {
    if (!geoData) return null
    let features = geoData.features
    if (filterType !== 'All')
      features = features.filter((f: any) => f.properties?.dominant_type === filterType)
    if (hiddenClusters.size > 0)
      features = features.filter((f: any) => !hiddenClusters.has(f.properties?.cluster_id))
    return { ...geoData, features }
  }, [geoData, filterType, hiddenClusters])

  const filteredClusters = useMemo(() => {
    let result = clusters
    if (filterType !== 'All') result = result.filter(c => c.dominant_type === filterType)
    if (hiddenClusters.size > 0) result = result.filter(c => !hiddenClusters.has(c.id))
    return result
  }, [clusters, filterType, hiddenClusters])

  const geoKey = filterType + '|' + colorMode + '|' + [...hiddenClusters].sort().join(',')

  const toggleCluster = (id: string) =>
    setHiddenClusters(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const getColour = (id: string, dominantType: string) =>
    colorMode === 'cluster' ? (clusterColorMap.get(id) ?? '#888') : typeToColour(dominantType)

  return (
    <div style={{ position: 'relative', height: '100%', width: '100%' }}>
      {loading && (
        <div className="absolute inset-0 z-[2000] flex items-center justify-center bg-white/60">
          <div className="w-10 h-10 border-4 border-green-700 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Toolbar */}
      <div className="absolute top-3 left-3 z-[1000] flex flex-col gap-2">
        <div className="flex gap-2 items-center">
          <FilterBar active={filterType} onChange={setFilterType} />
          <button
            onClick={() => setColorMode(m => m === 'type' ? 'cluster' : 'type')}
            className={`px-3 py-1 rounded-full text-sm font-medium shadow
              ${colorMode === 'cluster' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-700 border border-gray-300'}`}
          >
            Clusters
          </button>
        </div>

        {/* Cluster list panel */}
        {colorMode === 'cluster' && clusters.length > 0 && (
          <div className="bg-white rounded-lg shadow-lg border border-gray-200 w-56">
            <div className="flex justify-between items-center px-3 py-2 border-b border-gray-100">
              <span className="text-xs font-semibold text-gray-600">
                {hiddenClusters.size > 0 ? `${hiddenClusters.size} hidden` : 'All visible'}
              </span>
              {hiddenClusters.size > 0 && (
                <button
                  onClick={() => setHiddenClusters(new Set())}
                  className="text-xs text-indigo-600 hover:underline"
                >
                  Show all
                </button>
              )}
            </div>
            <div style={{ maxHeight: '50vh', overflowY: 'auto' }}>
              {clusters.map(c => {
                const hidden = hiddenClusters.has(c.id)
                return (
                  <div
                    key={c.id}
                    onClick={() => toggleCluster(c.id)}
                    className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer hover:bg-gray-50 ${hidden ? 'opacity-40' : ''}`}
                  >
                    <span
                      className="w-3 h-3 rounded-full flex-shrink-0"
                      style={{ background: clusterColorMap.get(c.id) ?? '#888' }}
                    />
                    <span className="text-xs text-gray-700 truncate">{c.name}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

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
            key={geoKey}
            data={filteredGeo}
            style={(feature) => ({
              fillColor: getColour(
                feature?.properties?.cluster_id ?? '',
                feature?.properties?.dominant_type ?? ''
              ),
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
              fillColor: getColour(forest.id, forest.dominant_type),
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
