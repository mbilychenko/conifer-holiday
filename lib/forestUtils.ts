export function typeToColour(dominant_type: string): string {
  switch (dominant_type) {
    case 'Conifer':              return '#1a5c1a'
    case 'Mixed mainly conifer': return '#3d8b3d'
    default:                     return '#6b8e23'
  }
}

export function typeToLabel(dominant_type: string): string {
  switch (dominant_type) {
    case 'Conifer':              return 'Conifer'
    case 'Mixed mainly conifer': return 'Mixed conifer'
    default:                     return dominant_type
  }
}
