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
