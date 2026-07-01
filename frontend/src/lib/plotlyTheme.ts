import type { Layout } from 'plotly.js'

export const miraiChartColors = {
  axis: '#1E293B',
  axisMuted: '#334155',
  grid: '#D9E2EC',
  zeroLine: '#94A3B8',
  reference: '#475569',
  darkAxis: '#E8EEF8',
  darkMuted: '#C7D2E4',
  darkGrid: 'rgba(199, 210, 228, 0.22)',
  darkZeroLine: 'rgba(232, 238, 248, 0.48)',
}

const fontFamily = 'Inter, Aptos, Avenir Next, ui-sans-serif, system-ui, sans-serif'

type LayoutOverride = Partial<Layout>

type AxisLayout = NonNullable<Layout['xaxis']>

function mergeAxis(base: AxisLayout, override?: AxisLayout): AxisLayout {
  return {
    ...base,
    ...override,
    title: {
      ...(typeof base.title === 'object' ? base.title : {}),
      ...(typeof override?.title === 'object' ? override.title : {}),
      font: {
        ...(typeof base.title === 'object' && typeof base.title.font === 'object' ? base.title.font : {}),
        ...(typeof override?.title === 'object' && typeof override.title.font === 'object' ? override.title.font : {}),
      },
    },
    tickfont: {
      ...(typeof base.tickfont === 'object' ? base.tickfont : {}),
      ...(typeof override?.tickfont === 'object' ? override.tickfont : {}),
    },
  }
}

function mergeLayout(base: LayoutOverride, override: LayoutOverride = {}): LayoutOverride {
  return {
    ...base,
    ...override,
    margin: { ...base.margin, ...override.margin },
    font: { ...base.font, ...override.font },
    legend: {
      ...base.legend,
      ...override.legend,
      font: {
        ...(typeof base.legend?.font === 'object' ? base.legend.font : {}),
        ...(typeof override.legend?.font === 'object' ? override.legend.font : {}),
      },
    },
    xaxis: mergeAxis(base.xaxis ?? {}, override.xaxis),
    yaxis: mergeAxis(base.yaxis ?? {}, override.yaxis),
  }
}

export function lightPlotOnDarkCardLayout(overrides: LayoutOverride = {}): LayoutOverride {
  const base: LayoutOverride = {
    paper_bgcolor: 'rgba(255,255,255,0)',
    plot_bgcolor: '#FFFFFF',
    margin: { l: 62, r: 28, t: 34, b: 58 },
    font: { family: fontFamily, color: miraiChartColors.axis, size: 12 },
    legend: {
      orientation: 'h',
      y: -0.24,
      font: { family: fontFamily, color: miraiChartColors.darkAxis, size: 12 },
    },
    xaxis: {
      automargin: true,
      gridcolor: miraiChartColors.grid,
      zerolinecolor: miraiChartColors.zeroLine,
      tickfont: { family: fontFamily, color: miraiChartColors.axis, size: 11 },
      title: { font: { family: fontFamily, color: miraiChartColors.axis, size: 12 } },
    },
    yaxis: {
      automargin: true,
      gridcolor: miraiChartColors.grid,
      zerolinecolor: miraiChartColors.zeroLine,
      tickfont: { family: fontFamily, color: miraiChartColors.axis, size: 11 },
      title: { font: { family: fontFamily, color: miraiChartColors.axis, size: 12 } },
    },
  }
  return mergeLayout(base, overrides)
}

export function transparentDarkPlotLayout(overrides: LayoutOverride = {}): LayoutOverride {
  const base: LayoutOverride = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    margin: { l: 58, r: 28, t: 30, b: 58 },
    font: { family: fontFamily, color: miraiChartColors.darkAxis, size: 12 },
    legend: {
      orientation: 'h',
      y: 1.14,
      font: { family: fontFamily, color: miraiChartColors.darkAxis, size: 12 },
    },
    xaxis: {
      automargin: true,
      gridcolor: miraiChartColors.darkGrid,
      zerolinecolor: miraiChartColors.darkZeroLine,
      tickfont: { family: fontFamily, color: miraiChartColors.darkAxis, size: 11 },
      title: { font: { family: fontFamily, color: miraiChartColors.darkAxis, size: 12 } },
    },
    yaxis: {
      automargin: true,
      gridcolor: miraiChartColors.darkGrid,
      zerolinecolor: miraiChartColors.darkZeroLine,
      tickfont: { family: fontFamily, color: miraiChartColors.darkAxis, size: 11 },
      title: { font: { family: fontFamily, color: miraiChartColors.darkAxis, size: 12 } },
    },
  }
  return mergeLayout(base, overrides)
}

export const plotConfig = { responsive: true, displaylogo: false }
