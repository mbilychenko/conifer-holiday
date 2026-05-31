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

// Golden-angle spread gives 100 visually distinct hues
export function clusterToColour(index: number): string {
  const hue = (index * 137.508) % 360
  return `hsl(${hue.toFixed(0)}, 60%, 42%)`
}
