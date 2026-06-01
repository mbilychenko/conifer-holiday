export interface ForestCluster {
  id: string
  name: string
  country: 'England' | 'Scotland' | 'Wales'
  dominant_type: string
  hectares: number
  polygon_count: number
  lat: number
  lng: number
  googlePlaceId?: string | null
  description?: string | null
}

export interface DestinationReview {
  author: string
  rating: number | null
  text: string
  relative_time: string
}

export interface PlacesData {
  place_id: string | null
  canonical_name: string | null
  rating: number | null
  review_count: number | null
  google_maps_uri: string | null
  website: string | null
  editorial_summary: string | null
  address: string | null
  opening_hours: string[]
  reviews: DestinationReview[]
  photo_paths: string[]
}

export interface Destination {
  cluster_id: string
  cluster_name: string
  osm_id: string
  osm_type: 'way' | 'relation'
  name: string
  area_ha: number
  centroid_lat: number
  centroid_lng: number
  places_data: PlacesData | null
  match_method: string | null
}

export interface TransitResult {
  durationText: string
  durationSeconds: number
  steps: TransitStep[]
}

export interface TransitStep {
  instruction: string
  mode: 'WALK' | 'TRAIN' | 'BUS' | 'SUBWAY'
  durationText: string
  departureStop?: string
  arrivalStop?: string
  line?: string
}

export interface PlacesResult {
  rating?: number
  reviewCount?: number
  reviews: PlaceReview[]
  photoUri?: string
  editorialSummary?: string
}

export interface PlaceReview {
  authorName: string
  rating: number
  text: string
  relativeTime: string
}
