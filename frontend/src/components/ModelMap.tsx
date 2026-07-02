import { useEffect, useMemo, useRef, useState } from 'react'
import type { MutableRefObject, RefObject } from 'react'
import type { ProjectSchema } from '../lib/api'

type SchemaInput = ProjectSchema['inputs'][number]
type SchemaOutput = ProjectSchema['outputs'][number]

type ModelArchitectureMetadata = {
  hiddenLayers?: number[]
  labels?: string[]
}

type ModelMapProps = {
  inputs: SchemaInput[]
  outputs: SchemaOutput[]
  modelName: string
  modelRuntime?: string
  modelStatus?: string
  architecture?: ModelArchitectureMetadata
}

type Point = { x: number; y: number }
type Connection = { from: Point; to: Point; emphasis?: boolean }

function displayName(variable: { label?: string; name: string }) {
  return variable.label || variable.name.replace(/_/g, ' ')
}

function unitLabel(variable: { unit?: string }) {
  return variable.unit?.trim() || 'schema variable'
}

function directionLabel(output: SchemaOutput) {
  return output.direction === 'minimize' ? 'Minimize' : 'Maximize'
}

function boundsLabel(input: SchemaInput) {
  if (typeof input.min !== 'number' || typeof input.max !== 'number') return null
  const unit = input.unit ? ` ${input.unit}` : ''
  return `${input.min.toLocaleString()}–${input.max.toLocaleString()}${unit}`
}

function sampleIndexes(length: number, maxCount: number) {
  if (length <= maxCount) return Array.from({ length }, (_, index) => index)
  if (maxCount <= 1) return [0]
  return Array.from({ length: maxCount }, (_, index) => Math.round(index * (length - 1) / (maxCount - 1)))
}

function portCenter(port: Element | null, wrapper: HTMLElement | null): Point | null {
  if (!port || !wrapper) return null
  const portRect = port.getBoundingClientRect()
  const wrapperRect = wrapper.getBoundingClientRect()
  return {
    x: portRect.left + portRect.width / 2 - wrapperRect.left,
    y: portRect.top + portRect.height / 2 - wrapperRect.top,
  }
}

function HiddenRepresentation({ architecture, firstHiddenRefs, latentRefs }: {
  architecture?: ModelArchitectureMetadata
  firstHiddenRefs: MutableRefObject<(SVGCircleElement | null)[]>
  latentRefs: MutableRefObject<(SVGCircleElement | null)[]>
}) {
  const stageRef = useRef<HTMLDivElement>(null)
  const [stageSize, setStageSize] = useState({ width: 900, height: 520 })

  useEffect(() => {
    const update = () => {
      const rect = stageRef.current?.getBoundingClientRect()
      if (!rect) return
      setStageSize({ width: Math.max(1, rect.width), height: Math.max(1, rect.height) })
    }
    update()
    const observer = new ResizeObserver(update)
    if (stageRef.current) observer.observe(stageRef.current)
    window.addEventListener('resize', update)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [])

  const labels = architecture?.labels?.length
    ? architecture.labels.slice(0, 4)
    : ['Hidden layer 1', 'Hidden layer 2', 'Latent representation']
  const layerSizes = architecture?.hiddenLayers?.length
    ? architecture.hiddenLayers.slice(0, labels.length).map((size) => Math.max(4, Math.min(9, Math.round(size / 16))))
    : [8, 6, 4].slice(0, labels.length)
  const { width, height } = stageSize
  const labelY = height * 0.08
  const unitY = height * 0.125
  const yMin = height * 0.22
  const yMax = height * 0.84
  const layerFractions = labels.length === 3 ? [0.12, 0.5, 0.88] : labels.map((_, index) => 0.12 + index * (0.76 / Math.max(labels.length - 1, 1)))
  const nodeRadius = Math.max(14, Math.min(21, Math.min(width, height) * 0.036))
  const haloRadius = nodeRadius * 1.42
  const innerRadius = nodeRadius * 0.52
  const layers = labels.map((label, layerIndex) => ({
    label,
    nodes: Array.from({ length: layerSizes[layerIndex] ?? 4 }, (_, nodeIndex) => ({
      x: width * (layerFractions[layerIndex] ?? 0.5),
      y: layerSizes[layerIndex] === 1 ? (yMin + yMax) / 2 : yMin + nodeIndex * ((yMax - yMin) / Math.max((layerSizes[layerIndex] ?? 4) - 1, 1)),
    })),
  }))
  const edges = layers.slice(0, -1).flatMap((layer, layerIndex) =>
    layer.nodes.flatMap((from, fromIndex) =>
      layers[layerIndex + 1].nodes
        .filter((_, toIndex) => (fromIndex + toIndex + layerIndex) % 2 === 0)
        .map((to) => ({ from, to, active: (fromIndex + layerIndex) % 3 === 0 })),
    ),
  )

  return (
    <div ref={stageRef} className="h-full min-h-[320px] w-full lg:min-h-[360px]">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full overflow-visible" preserveAspectRatio="none" role="img" aria-label="Hidden representation inside the neural surrogate model">
        <defs>
          <filter id="hidden-node-glow" x="-45%" y="-45%" width="190%" height="190%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        {edges.map((edge, index) => (
          <path
            key={`hidden-edge-${index}`}
            d={`M ${edge.from.x} ${edge.from.y} C ${edge.from.x + (edge.to.x - edge.from.x) * 0.46} ${edge.from.y}, ${edge.to.x - (edge.to.x - edge.from.x) * 0.46} ${edge.to.y}, ${edge.to.x} ${edge.to.y}`}
            fill="none"
            stroke={edge.active ? 'rgba(216, 201, 155, 0.78)' : 'rgba(226, 232, 240, 0.22)'}
            strokeWidth={edge.active ? 2.3 : 1.35}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {layers.map((layer, layerIndex) => layer.nodes.map((node, nodeIndex) => {
          const isFirstHidden = layerIndex === 0
          const isLatent = layerIndex === layers.length - 1
          return (
            <g key={`hidden-node-${layerIndex}-${nodeIndex}`} filter={isLatent ? 'url(#hidden-node-glow)' : undefined}>
              <circle
                ref={(element) => {
                  if (isFirstHidden) firstHiddenRefs.current[nodeIndex] = element
                  if (isLatent) latentRefs.current[nodeIndex] = element
                }}
                cx={node.x}
                cy={node.y}
                r={isLatent ? nodeRadius * 1.12 : nodeRadius}
                fill={isLatent ? '#74C7F5' : '#0B1220'}
                opacity="0.96"
              />
              <circle cx={node.x} cy={node.y} r={isLatent ? haloRadius * 1.18 : haloRadius} fill="none" stroke="rgba(216, 201, 155, 0.28)" vectorEffect="non-scaling-stroke" />
              <circle cx={node.x} cy={node.y} r={innerRadius} fill="rgba(5, 9, 24, 0.22)" stroke="rgba(255,255,255,0.26)" strokeWidth="0.7" vectorEffect="non-scaling-stroke" />
            </g>
          )
        }))}
        {layers.map((layer, layerIndex) => (
          <g key={layer.label}>
            <text x={layer.nodes[0]?.x ?? 0} y={labelY} fill={layerIndex === layers.length - 1 ? 'rgba(216,201,155,0.92)' : 'rgba(251,250,245,0.74)'} fontSize="13" fontWeight="800" textAnchor="middle">
              {layer.label}
            </text>
            <text x={layer.nodes[0]?.x ?? 0} y={unitY} fill="rgba(251,250,245,0.42)" fontSize="10" fontWeight="700" textAnchor="middle">
              {layer.nodes.length} units
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

function VariableCard({ input, index, compact, portRef }: { input: SchemaInput; index: number; compact: boolean; portRef: (element: HTMLSpanElement | null) => void }) {
  return (
    <div className={`group relative flex items-center gap-3 rounded-lg border border-slate-200 bg-[#0D1B2D] pr-5 transition hover:border-[#74C7F5] hover:bg-[#10203A] ${compact ? 'px-3 py-2' : 'px-3 py-3'}`}>
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-[#74C7F5]/60 bg-[#0D1B2D] text-xs font-bold text-[#2F6BFF]">{index + 1}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-white" title={displayName(input)}>{displayName(input)}</div>
        <div className="truncate text-xs text-slate-400">{boundsLabel(input) || unitLabel(input)}</div>
      </div>
      <span ref={portRef} className="absolute -right-2 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-white bg-[#2F6BFF] shadow-md shadow-[#2F6BFF]/20" aria-hidden="true" />
    </div>
  )
}

function OutputCard({ output, compact, portRef }: { output: SchemaOutput; compact: boolean; portRef: (element: HTMLSpanElement | null) => void }) {
  return (
    <div className={`relative rounded-lg border border-slate-200 bg-[#0D1B2D] transition hover:border-[#74C7F5] hover:bg-[#10203A] ${compact ? 'p-3 pl-5' : 'p-4 pl-5'}`}>
      <span ref={portRef} className="absolute -left-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full border-[3px] border-white bg-[#74C7F5] shadow-sm shadow-[#74C7F5]/40 ring-2 ring-[#74C7F5]/20" aria-hidden="true" />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 text-sm font-semibold leading-5 text-white" title={displayName(output)}>{displayName(output)}</div>
        <span className={`shrink-0 rounded-full px-2 py-1 text-[0.62rem] font-bold tracking-normal ${output.direction === 'minimize' ? 'bg-rose-950/40 text-rose-200 ring-1 ring-rose-400/30' : 'bg-[#0D1B2D] text-[#BDEAFF] ring-1 ring-[#74C7F5]/30'}`}>
          {directionLabel(output)}
        </span>
      </div>
      <div className="mt-1 text-xs text-slate-400">{unitLabel(output)}</div>
    </div>
  )
}

function ConnectionOverlay({ wrapperRef, inputPorts, outputPorts, firstHiddenNodes, latentNodes }: {
  wrapperRef: RefObject<HTMLDivElement>
  inputPorts: MutableRefObject<(HTMLSpanElement | null)[]>
  outputPorts: MutableRefObject<(HTMLSpanElement | null)[]>
  firstHiddenNodes: MutableRefObject<(SVGCircleElement | null)[]>
  latentNodes: MutableRefObject<(SVGCircleElement | null)[]>
}) {
  const [connections, setConnections] = useState<Connection[]>([])
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const update = () => {
      const wrapper = wrapperRef.current
      if (!wrapper) return
      const wrapperRect = wrapper.getBoundingClientRect()
      const firstHiddenCenters = firstHiddenNodes.current.map((node) => portCenter(node, wrapper)).filter((point): point is Point => Boolean(point))
      const latentCenters = latentNodes.current.map((node) => portCenter(node, wrapper)).filter((point): point is Point => Boolean(point))
      const isDesktop = wrapperRect.width >= 980
      setSize({ width: wrapperRect.width, height: wrapperRect.height })
      if (!isDesktop || !firstHiddenCenters.length || !latentCenters.length) {
        setConnections([])
        return
      }
      const inputIndexes = sampleIndexes(inputPorts.current.length, inputPorts.current.length > 12 ? 10 : inputPorts.current.length)
      const outputIndexes = sampleIndexes(outputPorts.current.length, outputPorts.current.length > 10 ? 8 : outputPorts.current.length)
      const next: Connection[] = []
      const connectionsPerInput = inputPorts.current.length <= 8 ? 2 : 1
      inputIndexes.forEach((index) => {
        const from = portCenter(inputPorts.current[index], wrapper)
        if (!from) return
        for (let offset = 0; offset < connectionsPerInput; offset += 1) {
          const hiddenIndex = (index * 2 + offset * 3) % firstHiddenCenters.length
          next.push({ from, to: firstHiddenCenters[hiddenIndex], emphasis: offset === 0 && (index === 0 || index === inputPorts.current.length - 1 || index % 3 === 0) })
        }
      })
      outputIndexes.forEach((index) => {
        const to = portCenter(outputPorts.current[index], wrapper)
        if (!to) return
        const from = latentCenters[(index * 2) % latentCenters.length]
        next.push({ from, to, emphasis: index === 0 || index === outputPorts.current.length - 1 || index % 3 === 0 })
      })
      setConnections(next)
    }
    update()
    const observer = new ResizeObserver(update)
    if (wrapperRef.current) observer.observe(wrapperRef.current)
    window.addEventListener('resize', update)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [firstHiddenNodes, inputPorts, latentNodes, outputPorts, wrapperRef])

  if (!connections.length) return null
  return (
    <svg className="pointer-events-none absolute inset-0 z-30 hidden xl:block" width={size.width} height={size.height} aria-hidden="true">
      <defs>
        <linearGradient id="model-map-flow" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#2F6BFF" stopOpacity="0.62" />
          <stop offset="50%" stopColor="#74C7F5" stopOpacity="0.72" />
          <stop offset="100%" stopColor="#2F6BFF" stopOpacity="0.5" />
        </linearGradient>
      </defs>
      {connections.map((connection, index) => {
        const dx = connection.to.x - connection.from.x
        const c1x = connection.from.x + dx * 0.42
        const c2x = connection.to.x - dx * 0.42
        return (
          <path
            key={`flow-${index}`}
            d={`M ${connection.from.x} ${connection.from.y} C ${c1x} ${connection.from.y}, ${c2x} ${connection.to.y}, ${connection.to.x} ${connection.to.y}`}
            fill="none"
            stroke="url(#model-map-flow)"
              strokeWidth={connection.emphasis ? 2.35 : 1.45}
            strokeOpacity={connection.emphasis ? 0.88 : 0.5}
          />
        )
      })}
    </svg>
  )
}

export function ModelMap({ inputs, outputs, modelName, modelRuntime = 'ONNX Runtime', modelStatus = 'Served model · current', architecture }: ModelMapProps) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const inputPorts = useRef<(HTMLSpanElement | null)[]>([])
  const outputPorts = useRef<(HTMLSpanElement | null)[]>([])
  const firstHiddenNodes = useRef<(SVGCircleElement | null)[]>([])
  const latentNodes = useRef<(SVGCircleElement | null)[]>([])
  const compactInputs = inputs.length > 8
  const compactOutputs = outputs.length > 8
  const inputScroll = inputs.length > 10
  const outputScroll = outputs.length > 10
  const visibleConnectionNote = useMemo(() => {
    if (inputs.length > 10 || outputs.length > 8) return 'Representative flow lines shown to avoid visual clutter.'
    return 'Input and output cards act as the visible model layers.'
  }, [inputs.length, outputs.length])

  return (
    <section id="design-model-flow" className="scroll-mt-8 overflow-hidden rounded-[2.2rem] border border-slate-200/80 bg-white/95 p-6 shadow-sm shadow-slate-900/10 backdrop-blur">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-xs font-semibold tracking-normal text-[#74C7F5]">ML Model Map</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-slate-950">From experiment settings to predicted response</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
            The surrogate model maps the active project&apos;s controlled variables into predicted KPIs used by the recommendation engine.
          </p>
        </div>
      </div>

      <div ref={wrapperRef} className="relative mt-6">
        <ConnectionOverlay wrapperRef={wrapperRef} inputPorts={inputPorts} outputPorts={outputPorts} firstHiddenNodes={firstHiddenNodes} latentNodes={latentNodes} />
        <div className="relative z-20 grid gap-5 xl:grid-cols-[0.9fr_1.45fr_0.95fr] xl:items-stretch">
          <div className="rounded-xl border border-slate-200 bg-[#0B1220] p-5">
            <div className="text-[0.72rem] font-bold tracking-normal text-[#74C7F5]">Controlled variables</div>
            <div className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-white">{inputs.length} variables</div>
            <p className="mt-2 text-sm leading-6 text-slate-300">Project-specific settings defined by the active schema.</p>
            <div className={`mt-5 space-y-2 pr-1 ${inputScroll ? 'max-h-[24rem] overflow-y-auto' : ''}`}>
              {inputs.map((input, index) => (
                <VariableCard key={input.name} input={input} index={index} compact={compactInputs} portRef={(element) => { inputPorts.current[index] = element }} />
              ))}
            </div>
          </div>

          <div className="relative flex h-full min-h-[520px] flex-col overflow-hidden rounded-xl border border-slate-800 bg-[#050918] p-4 text-white shadow-sm shadow-slate-950/20">
            <div className="pointer-events-none absolute -right-16 -top-20 h-48 w-48 rounded-full bg-[#74C7F5]/10 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-24 left-16 h-52 w-52 rounded-full bg-[#2F6BFF]/20 blur-3xl" />
            <div className="relative flex min-h-0 flex-1 flex-col">
              <header className="shrink-0">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                  <span className="rounded-full border border-[#74C7F5]/40 bg-[#74C7F5]/12 px-3 py-1 text-[0.68rem] font-bold tracking-normal text-[#BDEAFF]">
                    {modelRuntime} &middot; {modelStatus}
                  </span>
                </div>
                <div className="text-[0.68rem] font-bold tracking-normal text-[#74C7F5]">Neural surrogate</div>
                <div className="truncate text-base font-semibold tracking-[-0.03em] text-white/95" title={modelName}>{modelName}</div>
              </header>

              <div className="flex min-h-[320px] flex-1 items-stretch justify-center py-3 lg:min-h-[460px]">
                <div className="flex h-full min-h-[320px] w-full items-stretch justify-center rounded-[1.6rem] border border-white/10 bg-white/[0.035] px-3 py-2 lg:min-h-[460px]">
                  <HiddenRepresentation architecture={architecture} firstHiddenRefs={firstHiddenNodes} latentRefs={latentNodes} />
                </div>
              </div>

              <footer className="shrink-0 truncate rounded-full border border-white/10 bg-white/[0.025] px-4 py-1.5 text-[0.7rem] leading-5 text-white/45">
                Schema cards are the visible input/output layers; the center shows the learned hidden representation.
              </footer>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-[#0B1220] p-5">
            <div className="text-[0.72rem] font-bold tracking-normal text-[#74C7F5]">Predicted response</div>
            <div className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-white">{outputs.length} KPIs</div>
            <p className="mt-2 text-sm leading-6 text-slate-300">Schema-defined model outputs used for scoring, search, and tradeoff review.</p>
            <div className={`mt-5 flex flex-col gap-2 pl-1 ${outputScroll ? 'max-h-[24rem] overflow-y-auto' : 'xl:min-h-[26rem] xl:justify-center'}`}>
              {outputs.map((output, index) => (
                <OutputCard key={output.name} output={output} compact={compactOutputs} portRef={(element) => { outputPorts.current[index] = element }} />
              ))}
            </div>
          </div>
        </div>
      </div>
      <p className="mt-4 rounded-md border border-slate-700 bg-[#0D1B2D] px-4 py-3 text-xs leading-5 text-slate-300">
        Inputs and outputs are generated from the active project schema. {visibleConnectionNote}
      </p>
    </section>
  )
}
