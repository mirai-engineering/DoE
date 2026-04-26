import 'plotly.js'
import type { ColorScale } from 'plotly.js'

declare module 'plotly.js' {
  interface ScatterLine {
    cmin?: number
    cmax?: number
    colorscale?: ColorScale
    showscale?: boolean
    colorbar?: { title?: { text?: string } }
  }

  interface PlotData {
    dimensions?: Array<{
      label: string
      values: number[]
      range?: [number, number]
    }>
  }
}
