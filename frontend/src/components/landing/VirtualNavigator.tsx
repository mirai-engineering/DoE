import { lazy, Suspense, useEffect, useRef, useState } from 'react'

const NAVIGATOR_STAGES = [
  {
    num: '01', id: 'raw', label: 'Raw Experiments',
    headline: 'Historical test data exists across files, protocols, and isolated test runs.',
    body: 'Mirai ingests fragmented bench data while preserving provenance from the lab to the model.',
    metrics: ['47 historical runs', '12 source files', '6 controlled variables'],
  },
  {
    num: '02', id: 'structured', label: 'Structured Space',
    headline: 'Mirai maps variables, metadata, and test conditions into one traceable experiment table.',
    body: 'Every variable, protocol, and unit is captured — so the same data can power preprocessing, validation, and modeling without repeated clean-up.',
    metrics: ['7 inputs', '4 outputs', '100% variables mapped'],
  },
  {
    num: '03', id: 'surrogate', label: 'Validated Surrogate',
    headline: 'A surrogate model learns the response surface and shows where predictions are reliable.',
    body: 'Validation diagnostics, calibration, and uncertainty estimation prevent overconfident recommendations.',
    metrics: ['R² 0.89', 'Domain coverage 96%', 'Prediction uncertainty: moderate'],
  },
  {
    num: '04', id: 'optimize', label: 'Multi-Objective Search',
    headline: 'Mirai evaluates feasible virtual candidates across competing engineering objectives.',
    body: 'Thousands of virtual experiments are ranked before a single physical test is committed.',
    metrics: ['10,000 candidates', '3 objectives', 'Top 1% highlighted'],
  },
  {
    num: '05', id: 'recommended', label: 'Recommended Run',
    headline: 'A validated model becomes a decision-ready next physical test.',
    body: 'The platform ranks candidates with explicit trade-offs, uncertainty, and expected value — so engineers can review and trust the recommendation.',
    metrics: ['C-017 selected', 'High confidence', 'Performance +12.6%'],
  },
]

const ExperimentChamber = lazy(() => import('./ExperimentChamber'))

function usePrefersReducedMotion() {
  const [reduce, setReduce] = useState(false)

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduce(query.matches)
    const onChange = () => setReduce(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return reduce
}

function ProgressRail({ stageIdx, progress }: { stageIdx: number; progress: number }) {
  return (
    <div className="relative space-y-0">
      {NAVIGATOR_STAGES.map((stage, index) => {
        const active = index === stageIdx
        const done = index < stageIdx
        return (
          <div key={stage.id} className="flex items-center gap-3 py-1.5">
            <span className={`min-w-[22px] font-mono text-[11px] tracking-wider transition-all duration-500 ${active ? 'font-medium text-[#7C5CFF]' : done ? 'text-[#63D7FF]/60' : 'text-[#5A6B89]/30'}`}>
              {stage.num}
            </span>
            <div className={`h-px transition-all duration-700 ${active ? 'w-8 bg-[#7C5CFF]/60' : done ? 'w-6 bg-[#63D7FF]/40' : 'w-6 bg-[#5A6B89]/10'}`} />
            <span className={`font-mono text-[10px] uppercase tracking-wider transition-all duration-500 ${active ? 'font-medium text-[#F6F4EA]' : done ? 'text-[#9BA8C0]/60' : 'text-[#5A6B89]/25'}`}>
              {stage.label}
            </span>
            {active && <div className="h-1.5 w-1.5 rounded-full bg-[#7C5CFF] shadow-[0_0_6px_rgba(109,93,251,0.6)]" />}
          </div>
        )
      })}
      <div className="absolute bottom-[18px] left-[11px] top-[18px] -z-10 w-px bg-[#5A6B89]/10" />
      <div className="absolute left-[11px] top-[18px] -z-10 w-px bg-gradient-to-b from-[#7C5CFF] via-[#63D7FF]/40 to-transparent transition-all duration-300" style={{ height: `${progress * 100}%` }} />
    </div>
  )
}

function NarrativePanel({ stageIdx, stageT, progress }: { stageIdx: number; stageT: number; progress: number }) {
  const stage = NAVIGATOR_STAGES[stageIdx]
  const contentAlpha = stageIdx === 0 ? Math.min(1, stageT * 3) : 1

  return (
    <div className="flex h-full select-none flex-col justify-center px-8 lg:px-12 xl:px-14">
      <p className="mb-6 font-mono text-[9px] tracking-[0.2em] text-[#7C5CFF]/70">THE EXPERIMENT NAVIGATOR</p>
      <ProgressRail stageIdx={stageIdx} progress={progress} />
      <div className="mt-8 space-y-4" style={{ opacity: contentAlpha }}>
        <p className="font-mono text-[11px] tracking-[0.15em] text-[#7C5CFF]">{stage.num} / {stage.label.toUpperCase()}</p>
        <h3 className="text-2xl font-semibold leading-[1.15] tracking-tight text-[#F6F4EA] sm:text-[1.6rem]">{stage.headline}</h3>
        <p className="max-w-sm text-sm leading-relaxed text-[#9BA8C0]">{stage.body}</p>
        <div className="flex flex-wrap gap-x-5 gap-y-2 pt-1">
          {stage.metrics.map((metric) => (
            <div key={metric} className="flex items-center gap-2">
              <div className="h-1 w-1 rounded-full bg-[#7C5CFF]/50" />
              <span className="font-mono text-[10px] tracking-wide text-[#5A6B89]">{metric}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function LoadingChamber() {
  return (
    <div className="flex h-full w-full items-center justify-center" style={{ background: 'radial-gradient(ellipse at 60% 50%, #061226 0%, #030716 100%)' }}>
      <p className="font-mono text-[10px] tracking-[0.18em] text-[#7C5CFF]/40">Loading experiment chamber...</p>
    </div>
  )
}

function ScrollHint({ progress }: { progress: number }) {
  return (
    <div className="pointer-events-none absolute bottom-6 left-[35%] z-20 flex justify-center transition-opacity duration-700" style={{ opacity: Math.max(0, 1 - progress * 5) }}>
      <div className="flex items-center gap-2">
        <svg width="10" height="16" viewBox="0 0 10 16" className="text-[#7C5CFF]/30" aria-hidden="true">
          <rect x="1" y="1" width="8" height="14" rx="4" stroke="currentColor" strokeWidth="1" fill="none" />
          <circle cx="5" cy="5" r="1" fill="currentColor" className="animate-pulse" />
        </svg>
        <span className="font-mono text-[7px] tracking-widest text-[#5A6B89]/40">SCROLL TO EXPLORE</span>
      </div>
    </div>
  )
}

function EndCta({ progress }: { progress: number }) {
  const opacity = Math.max(0, Math.min(1, (progress - 0.88) / 0.07))
  return (
    <div className="pointer-events-none absolute bottom-8 left-[35%] z-20 flex justify-center" style={{ opacity }}>
      <a href="#proof" onClick={(event) => { event.preventDefault(); document.querySelector('#proof')?.scrollIntoView({ behavior: 'smooth' }) }} className="pointer-events-auto inline-flex h-9 items-center rounded-full border border-[#7C5CFF]/30 bg-[#0A1630]/60 px-5 text-[10px] font-medium tracking-wide text-[#9BA8C0] backdrop-blur-sm transition-all duration-200 hover:border-[#7C5CFF]/60 hover:text-[#F6F4EA]">
        See how Mirai ranks experiments
        <svg width="12" height="12" viewBox="0 0 12 12" className="ml-1.5 text-[#7C5CFF]/50" aria-hidden="true"><path d="M2.5 6h7M6 2.5l4 4-4 4" stroke="currentColor" strokeWidth="1.2" fill="none" /></svg>
      </a>
    </div>
  )
}

export function VirtualNavigator() {
  const reduce = usePrefersReducedMotion()
  const sectionRef = useRef<HTMLDivElement>(null)
  const [progress, setProgress] = useState(0)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setReady(true)
    const element = sectionRef.current
    if (!element) return

    const onScroll = () => {
      const rect = element.getBoundingClientRect()
      const viewportHeight = window.innerHeight
      const total = rect.height - viewportHeight
      if (total <= 0) {
        setProgress(0.5)
        return
      }
      setProgress(Math.max(0, Math.min(1, -rect.top / total)))
    }

    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const safeProgress = reduce ? 0.85 : progress
  const scaled = safeProgress * NAVIGATOR_STAGES.length
  const stageIdx = Math.min(NAVIGATOR_STAGES.length - 1, Math.max(0, Math.floor(scaled)))
  const stageT = Math.min(1, Math.max(0, scaled - stageIdx))

  return (
    <section ref={sectionRef} id="experiment-navigator" className="relative border-t border-violet-300/10 bg-[#010412]" style={{ height: reduce ? '100vh' : '500vh' }}>
      <div className="sticky top-0 h-[100dvh] w-full overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[#030716] via-[#050b1a] to-[#061226]" />
        <div className="absolute inset-0 opacity-[0.03] constellation-grid" />
        <div className="relative z-10 grid h-full grid-cols-1 lg:grid-cols-[35%_65%]">
          <div className="relative z-20 border-r border-violet-300/10">
            <NarrativePanel stageIdx={stageIdx} stageT={stageT} progress={safeProgress} />
            <div className="absolute bottom-6 left-8 font-mono text-[8px] tracking-wider text-[#5A6B89]/30">{stageIdx + 1} / 5</div>
          </div>
          {ready && (
            <div className="relative z-10 h-full w-full overflow-hidden">
              <Suspense fallback={<LoadingChamber />}>
                <ExperimentChamber progress={safeProgress} stageIdx={stageIdx} stageT={stageT} reduce={reduce} />
              </Suspense>
            </div>
          )}
        </div>
        <ScrollHint progress={safeProgress} />
        <EndCta progress={safeProgress} />
      </div>
    </section>
  )
}
