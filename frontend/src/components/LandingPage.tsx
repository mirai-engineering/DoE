import { useCallback, useEffect, useRef, useState } from 'react'
import { SignInButton, SignUpButton } from '@clerk/clerk-react'
import { VirtualNavigator } from './landing/VirtualNavigator'

const NAV_ITEMS = [
  { label: 'Workflow', href: '#workflow' },
  { label: 'Navigator', href: '#experiment-navigator' },
  { label: 'Proof', href: '#proof' },
  { label: 'Test Plans', href: '#test-plans' },
  { label: 'Industries', href: '#industries' },
]

const PAIN_POINTS = [
  { symptom: 'Fragmented sources', impact: "CSV dumps, lab notebooks, LIMS exports, sensor logs, and analysis scripts that don't agree." },
  { symptom: 'Untraceable preprocessing', impact: 'Critical transforms live in personal code and ad-hoc spreadsheets — hard to reproduce, impossible to audit.' },
  { symptom: 'Hidden model risk', impact: 'Surrogates without diagnostics lead to overconfidence, hidden extrapolation, and wasted test time.' },
  { symptom: 'Implicit trade-offs', impact: 'Performance vs. durability vs. cost decisions happen in meetings, not quantified frontiers.' },
]

const STAGES = [
  { number: '1', title: 'Data Package', desc: 'Upload multi-file test-bench exports. Mirai detects schemas, units, protocols, and provenance automatically.', meta: 'v4 / 12 sources / 3 protocols' },
  { number: '2', title: 'Structured Dataset', desc: 'Unified experiment table with validated schema, unit consistency, and missingness profile.', meta: '47 vars / 320 rows / validated' },
  { number: '3', title: 'Prepare & Validate', desc: 'Outlier detection, transform logging, leakage checks, and ML-readiness scoring.', meta: '4 transforms / 2 flags resolved' },
  { number: '4', title: 'Surrogate Model', desc: 'Train, tune, and validate surrogates with cross-validation, calibration, and uncertainty estimation.', meta: 'MLP / R² 0.85 / 5-fold CV' },
  { number: '5', title: 'Virtual Test Space', desc: 'Explore feasible candidates, weigh objectives, and inspect trade-offs on response surfaces.', meta: '320 candidates / 3 objectives' },
  { number: '6', title: 'Ranked Run Plan', desc: 'Export a ranked next-experiment plan with objective deltas, uncertainty, and constraint status.', meta: '5 candidates / 2 constraints' },
]

const INDUSTRIES = [
  { title: 'Fuel cells', objectives: 'Efficiency, durability, degradation rate, catalyst utilization' },
  { title: 'Batteries', objectives: 'Capacity retention, fast-charge, safety margins, cost' },
  { title: 'Materials', objectives: 'Strength, fatigue, corrosion, manufacturability' },
  { title: 'Electrolyzers', objectives: 'Efficiency, lifetime, operating window, stack cost' },
  { title: 'Advanced manufacturing', objectives: 'Yield, cycle time, defects, energy use' },
]

function scrollToHash(hash: string) {
  document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth' })
}

function MiraiLogo({ className = '' }: { className?: string }) {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className={className} aria-hidden="true">
      <rect width="28" height="28" rx="6" fill="#0A1630" />
      <g stroke="currentColor" strokeWidth="1.2" opacity="0.9">
        <line x1="14" y1="6" x2="14" y2="10" stroke="#6D5DFB" />
        <line x1="14" y1="18" x2="14" y2="22" stroke="#6D5DFB" />
        <line x1="6" y1="14" x2="10" y2="14" stroke="#3B82F6" />
        <line x1="18" y1="14" x2="22" y2="14" stroke="#3B82F6" />
        <circle cx="14" cy="14" r="5" stroke="#7C5CFF" fill="none" />
        <circle cx="14" cy="14" r="1.5" fill="#7C5CFF" />
      </g>
    </svg>
  )
}

function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleNav = useCallback((event: React.MouseEvent<HTMLAnchorElement>) => {
    const href = event.currentTarget.getAttribute('href')
    if (!href?.startsWith('#')) return
    event.preventDefault()
    scrollToHash(href)
    setMobileOpen(false)
  }, [])

  return (
    <header className={`fixed left-0 right-0 top-0 z-50 transition-all duration-300 ${scrolled ? 'border-b border-violet-400/10 bg-[#030716]/85 backdrop-blur-lg' : 'bg-transparent'}`}>
      <nav className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-6">
        <a href="#" onClick={handleNav} className="flex items-center gap-2.5" aria-label="Mirai DoE home">
          <MiraiLogo />
          <span className="text-sm font-medium tracking-tight text-[#F6F4EA]">
            Mirai <span className="ml-1 font-mono text-[10px] tracking-widest text-[#6D5DFB]">DOE</span>
          </span>
        </a>

        <div className="hidden items-center gap-8 md:flex">
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href} onClick={handleNav} className="text-sm text-[#9BA8C0] transition-colors duration-200 hover:text-[#F6F4EA]">
              {item.label}
            </a>
          ))}
          <a href="#cta" onClick={handleNav} className="inline-flex h-9 items-center rounded-full bg-[#6D5DFB]/90 px-5 text-xs font-medium tracking-wide text-white transition-all duration-200 hover:bg-[#6D5DFB]">
            Request a pilot
          </a>
        </div>

        <button onClick={() => setMobileOpen((open) => !open)} className="flex flex-col gap-1.5 p-2 md:hidden" aria-label="Toggle menu" aria-expanded={mobileOpen}>
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? 'translate-y-[3px] rotate-45' : ''}`} />
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? 'opacity-0' : ''}`} />
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? '-translate-y-[3px] -rotate-45' : ''}`} />
        </button>
      </nav>

      {mobileOpen && (
        <div className="border-t border-violet-400/10 bg-[#030716]/95 px-6 py-6 backdrop-blur-lg md:hidden">
          <div className="flex flex-col gap-3">
            {NAV_ITEMS.map((item) => (
              <a key={item.href} href={item.href} onClick={handleNav} className="text-sm text-[#9BA8C0] transition-colors hover:text-[#F6F4EA]">
                {item.label}
              </a>
            ))}
            <a href="#cta" onClick={handleNav} className="mt-2 inline-flex h-9 items-center justify-center rounded-full bg-[#6D5DFB]/90 px-5 text-xs font-medium tracking-wide text-white">
              Request a pilot
            </a>
          </div>
        </div>
      )}
    </header>
  )
}

function Hero() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const drawingCanvas = canvas
    const drawingContext = ctx

    let width = 0
    let height = 0
    let frame = 0
    let animationId = 0
    const points = Array.from({ length: 260 }, () => ({
      x: Math.random(),
      y: Math.random(),
      z: 0.3 + Math.random() * 0.7,
      recommended: Math.random() < 0.03,
      frontier: Math.random() < 0.08,
    }))

    function resize() {
      const scale = window.devicePixelRatio || 1
      width = drawingCanvas.offsetWidth * scale
      height = drawingCanvas.offsetHeight * scale
      drawingCanvas.width = width
      drawingCanvas.height = height
    }

    function draw() {
      const ctx = drawingContext
      ctx.clearRect(0, 0, width, height)
      const pad = width * 0.06
      const plotWidth = width - pad * 2
      const plotHeight = height - pad * 2

      ctx.strokeStyle = 'rgba(59, 130, 246, 0.06)'
      ctx.lineWidth = 0.5
      for (let i = 0; i <= 8; i += 1) {
        const gx = pad + (plotWidth / 8) * i
        const gy = pad + (plotHeight / 8) * i
        ctx.beginPath(); ctx.moveTo(gx, pad); ctx.lineTo(gx, pad + plotHeight); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(pad, gy); ctx.lineTo(pad + plotWidth, gy); ctx.stroke()
      }

      for (let c = 0; c < 4; c += 1) {
        ctx.beginPath()
        ctx.strokeStyle = `rgba(59, 130, 246, ${0.05 + c * 0.015})`
        const offset = c * 0.12 + Math.sin(frame * 0.004 + c * 1.5) * 0.015
        for (let t = 0; t <= 1; t += 0.015) {
          const x = pad + t * plotWidth
          const y = pad + plotHeight - (Math.sin(t * Math.PI * 2.5 + offset * 3) * 0.25 + 0.4 + offset * 0.8) * plotHeight
          if (t === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.stroke()
      }

      for (const point of points) {
        const x = pad + point.x * plotWidth + Math.sin(frame * 0.003 + point.x * 6) * 0.003 * plotWidth
        const y = pad + (1 - point.y) * plotHeight + Math.cos(frame * 0.004 + point.y * 5) * 0.003 * plotHeight
        if (point.recommended) {
          ctx.fillStyle = 'rgba(124, 92, 255, 0.7)'
          ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2); ctx.fill()
        } else if (point.frontier) {
          ctx.fillStyle = 'rgba(59, 130, 246, 0.35)'
          ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill()
        } else {
          ctx.fillStyle = `rgba(59, 130, 246, ${0.12 + point.z * 0.15})`
          ctx.beginPath(); ctx.arc(x, y, 1.5 + point.z * 0.5, 0, Math.PI * 2); ctx.fill()
        }
      }

      ctx.setLineDash([3, 5])
      ctx.beginPath()
      ctx.strokeStyle = 'rgba(124, 92, 255, 0.22)'
      for (let t = 0; t <= 1; t += 0.025) {
        const x = pad + (0.25 + t * 0.7) * plotWidth
        const y = pad + (1 - (1 - t * 0.45 + Math.sin(t * 7) * 0.035)) * plotHeight
        if (t === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.stroke()
      ctx.setLineDash([])

      frame += 1
      animationId = requestAnimationFrame(draw)
    }

    resize()
    window.addEventListener('resize', resize)
    animationId = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <section className="relative min-h-[100dvh] overflow-hidden bg-[#030716]">
      <div className="pointer-events-none absolute inset-0 opacity-25 constellation-grid" />
      <div className="pointer-events-none absolute -right-1/4 -top-1/3 h-2/3 w-1/2 rounded-full bg-[#6D5DFB]/10 blur-[150px]" />
      <div className="pointer-events-none absolute bottom-[-25%] left-0 h-1/2 w-1/2 rounded-full bg-[#3B82F6]/10 blur-[120px]" />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-[1400px] flex-col items-start justify-center px-6 pb-20 pt-24 lg:flex-row lg:items-center lg:gap-12">
        <div className="w-full max-w-[520px] shrink-0 lg:w-auto">
          <p className="mb-4 font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-[#7C5CFF]">ML-Guided Experiment Design</p>
          <h1 className="text-4xl font-semibold leading-[1.06] tracking-tight text-[#F6F4EA] sm:text-5xl lg:text-[3.25rem]">
            Design better experiments<br />
            <span className="text-[#7C5CFF]">before you run them.</span>
          </h1>
          <p className="mt-5 max-w-[460px] text-base leading-relaxed text-[#9BA8C0]">
            Mirai turns fragmented test-bench data into validated surrogate models and ranked next-test plans for industrial R&amp;D teams.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <a href="#workflow" onClick={(event) => { event.preventDefault(); scrollToHash('#workflow') }} className="inline-flex h-11 items-center rounded-full bg-[#6D5DFB]/90 px-7 text-sm font-medium tracking-wide text-white transition-all duration-200 hover:bg-[#6D5DFB]">
              Explore the platform
            </a>
            <SignInButton mode="modal">
              <button className="inline-flex h-11 items-center rounded-full border border-violet-300/20 px-7 text-sm font-medium tracking-wide text-[#9BA8C0] transition-all duration-200 hover:border-[#6D5DFB]/50 hover:text-[#F6F4EA]">
                Sign in to Mirai
              </button>
            </SignInButton>
          </div>

          <div className="mt-12 grid gap-5 sm:grid-cols-3">
            {[
              { icon: '03', label: 'Fewer Tests', desc: 'Virtual candidates before lab budget' },
              { icon: '02', label: 'Higher Confidence', desc: 'Validated surrogates with diagnostics' },
              { icon: '01', label: 'Better Decisions', desc: 'Ranked next-test plans with trade-offs' },
            ].map((feature) => (
              <div key={feature.label} className="space-y-1.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#3B82F6]">{feature.icon}</span>
                <p className="text-sm font-medium text-[#F6F4EA]">{feature.label}</p>
                <p className="text-xs leading-relaxed text-[#5A6B89]">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-12 w-full flex-1 lg:mt-0">
          <div className="relative overflow-hidden rounded-2xl border border-violet-300/20 bg-[#061226]/90 p-2">
            <div className="flex items-center justify-between border-b border-violet-300/10 px-3 py-2">
              <div className="flex items-center gap-3">
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#63D7FF]" />
                <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#63D7FF]">Model active</span>
                <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#5A6B89]">R² 0.85</span>
              </div>
              <span className="hidden font-mono text-[9px] uppercase tracking-[0.08em] text-[#7C5CFF] sm:inline">Navigation console</span>
            </div>
            <canvas ref={canvasRef} className="block h-[420px] w-full lg:h-[540px]" />
          </div>
        </div>
      </div>
    </section>
  )
}

function Problem() {
  return (
    <section className="relative border-t border-violet-300/10 bg-[#010412] py-28">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="grid gap-12 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <p className="mb-4 font-mono text-[0.6875rem] uppercase tracking-[0.15em] text-[#7C5CFF]">The problem</p>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Physical experiments are too valuable for trial-and-error.</h2>
            <p className="mt-4 text-sm leading-relaxed text-[#9BA8C0]">In industrial R&amp;D, the hardest part is turning fragmented results into consistent, reusable evidence for the next decision.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:col-span-3">
            {PAIN_POINTS.map((point) => (
              <div key={point.symptom} className="rounded-xl border border-violet-300/10 bg-[#0A1630] p-5">
                <p className="mb-1.5 font-mono text-[0.6875rem] uppercase tracking-[0.08em] text-[#3B82F6]">Symptom</p>
                <h3 className="text-sm font-medium text-[#F6F4EA]">{point.symptom}</h3>
                <div className="const-divider my-3" />
                <p className="text-xs leading-relaxed text-[#5A6B89]">{point.impact}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function Workflow() {
  return (
    <section id="workflow" className="relative border-t border-violet-300/10 bg-[#030716] py-28">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-2xl text-center">
          <p className="mb-4 font-mono text-[0.6875rem] uppercase tracking-[0.15em] text-[#7C5CFF]">The Mirai workflow</p>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">From fragmented data to ranked test plans.</h2>
          <p className="mt-4 text-sm leading-relaxed text-[#9BA8C0]">Each stage produces traceable artifacts that can be reviewed, reused, and improved.</p>
        </div>
        <div className="mt-12 flex flex-wrap justify-center gap-3">
          {STAGES.map((stage) => (
            <div key={stage.number} className="min-w-[180px] flex-1 rounded-xl border border-violet-300/10 bg-[#0A1630] p-4">
              <div className="mb-3 flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#6D5DFB]/15 text-[10px] font-semibold text-[#7C5CFF]">{stage.number}</span>
                <p className="text-sm font-medium text-[#F6F4EA]">{stage.title}</p>
              </div>
              <p className="text-xs leading-relaxed text-[#9BA8C0]">{stage.desc}</p>
              <div className="mt-3 rounded-lg border border-violet-300/10 bg-[#0D1D3D]/50 px-3 py-2">
                <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#5A6B89]">{stage.meta}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Proof() {
  return (
    <section id="proof" className="relative border-t border-violet-300/10 bg-[#030716] py-28">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-2xl text-center">
          <p className="mb-4 font-mono text-[0.6875rem] uppercase tracking-[0.15em] text-[#7C5CFF]">Product proof</p>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Recommendations are only as good as the model behind them.</h2>
          <p className="mt-4 text-sm leading-relaxed text-[#9BA8C0]">Mirai prioritizes model quality, traceability, and uncertainty so decisions are auditable and repeatable.</p>
        </div>
        <div className="mt-12 grid gap-4 sm:grid-cols-3">
          {[
            ['I', 'Ingest & Structure', 'Auto-detect schema, units, protocols, and provenance from multi-file bench exports.'],
            ['V', 'Validate & Diagnose', 'Cross-validation, residual analysis, calibration, and coverage maps are first-class outputs.'],
            ['R', 'Recommend with Trust', 'Predictions include confidence intervals and extrapolation risk flags on the design space.'],
          ].map(([mark, label, desc]) => (
            <div key={mark} className="rounded-xl border border-violet-300/10 bg-[#0A1630] p-6">
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-violet-300/20 bg-[#6D5DFB]/10">
                <span className="text-sm font-semibold text-[#7C5CFF]">{mark}</span>
              </div>
              <h3 className="text-base font-medium text-[#F6F4EA]">{label}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#5A6B89]">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function TestPlans() {
  return (
    <section id="test-plans" className="relative border-t border-violet-300/10 bg-[#010412] py-28">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="mb-4 font-mono text-[0.6875rem] uppercase tracking-[0.15em] text-[#7C5CFF]">Ranked test plans</p>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Make the next experiment explainable before it reaches the bench.</h2>
            <p className="mt-4 text-sm leading-relaxed text-[#9BA8C0]">Candidate plans expose objective weights, expected deltas, uncertainty, and constraint status so technical teams can discuss trade-offs with evidence.</p>
          </div>
          <div className="overflow-hidden rounded-2xl border border-violet-300/10 bg-[#0A1630]">
            {['C-017', 'C-042', 'C-108'].map((candidate, index) => (
              <div key={candidate} className="grid grid-cols-4 gap-3 border-b border-violet-300/10 p-4 last:border-b-0">
                <div>
                  <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#5A6B89]">Rank {index + 1}</p>
                  <p className="mt-1 text-sm font-medium text-[#F6F4EA]">{candidate}</p>
                </div>
                <div><p className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#5A6B89]">Perf.</p><p className="mt-1 text-sm text-[#63D7FF]">+{12 - index * 2}.6%</p></div>
                <div><p className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#5A6B89]">Risk</p><p className="mt-1 text-sm text-[#9BA8C0]">Low</p></div>
                <div><p className="font-mono text-[9px] uppercase tracking-[0.08em] text-[#5A6B89]">Status</p><p className="mt-1 text-sm text-[#7C5CFF]">Feasible</p></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function Industries() {
  return (
    <section id="industries" className="relative border-t border-violet-300/10 bg-[#030716] py-28">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-2xl text-center">
          <p className="mb-4 font-mono text-[0.6875rem] uppercase tracking-[0.15em] text-[#7C5CFF]">Industries</p>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Built for complex experiments where trade-offs are real.</h2>
          <p className="mt-4 text-sm leading-relaxed text-[#9BA8C0]">Start with one costly experimental workflow. Expand across teams, projects, and sites.</p>
        </div>
        <div className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {INDUSTRIES.map((industry) => (
            <div key={industry.title} className="relative overflow-hidden rounded-xl border border-violet-300/10 bg-[#0A1630] p-5 transition-all duration-300 hover:border-violet-300/30">
              <h3 className="text-base font-medium text-[#F6F4EA]">{industry.title}</h3>
              <svg viewBox="0 0 120 40" className="my-4 h-10 w-full opacity-40" aria-hidden="true">
                <path d="M5,30 Q30,25 60,20 Q90,15 115,10" stroke="rgba(59,130,246,0.4)" strokeWidth="0.5" fill="none" />
                <path d="M5,25 Q30,20 60,15 Q90,10 115,5" stroke="rgba(109,93,251,0.3)" strokeWidth="0.5" fill="none" />
              </svg>
              <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-[#5A6B89]">Typical objectives</p>
              <p className="text-xs leading-relaxed text-[#5A6B89]">{industry.objectives}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Cta() {
  return (
    <section id="cta" className="relative overflow-hidden border-t border-violet-300/10 bg-[#061226] py-28">
      <div className="pointer-events-none absolute inset-0 opacity-20 constellation-grid" />
      <div className="relative mx-auto max-w-[1400px] px-6">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <p className="mb-4 font-mono text-[0.6875rem] uppercase tracking-[0.15em] text-[#7C5CFF]">Mirai DoE Engine</p>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Make every physical test count.</h2>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-[#9BA8C0]">Walk through ingestion, traceability, surrogate diagnostics, and next-experiment recommendations for a representative slice of your bench data.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="mailto:hello@mirai.example?subject=Mirai%20DoE%20Engine%20%E2%80%94%20Demo%20Request" className="inline-flex h-11 items-center rounded-full bg-[#6D5DFB]/90 px-8 text-sm font-medium tracking-wide text-white transition-all duration-200 hover:bg-[#6D5DFB]">Request a pilot</a>
              <SignInButton mode="modal">
                <button className="inline-flex h-11 items-center rounded-full border border-violet-300/20 px-7 text-sm font-medium tracking-wide text-[#9BA8C0] transition-all duration-200 hover:border-[#6D5DFB]/50 hover:text-[#F6F4EA]">Sign in to Mirai</button>
              </SignInButton>
              <SignUpButton mode="modal">
                <button className="inline-flex h-11 items-center rounded-full border border-blue-300/20 px-7 text-sm font-medium tracking-wide text-[#9BA8C0] transition-all duration-200 hover:border-[#3B82F6]/50 hover:text-[#F6F4EA]">Create account</button>
              </SignUpButton>
            </div>
          </div>
          <div className="hidden lg:block">
            <svg viewBox="0 0 400 300" className="ml-auto w-full max-w-md opacity-60" aria-hidden="true">
              <defs><linearGradient id="cta-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="rgba(109,93,251,0.16)" /><stop offset="100%" stopColor="rgba(59,130,246,0.08)" /></linearGradient></defs>
              <rect width="400" height="300" fill="url(#cta-grad)" rx="12" />
              {[0, 1, 2, 3, 4].map((i) => <line key={`gx${i}`} x1={50 + i * 75} y1="40" x2={50 + i * 75} y2="260" stroke="rgba(59,130,246,0.08)" strokeWidth="0.5" />)}
              {[0, 1, 2].map((i) => <path key={`ct${i}`} d={`M50,${240 - i * 40} Q150,${180 - i * 30} 200,${160 - i * 25} Q280,${120 - i * 20} 350,${80 - i * 15}`} stroke="rgba(124,92,255,0.16)" strokeWidth="0.5" fill="none" />)}
              {Array.from({ length: 40 }, (_, i) => <circle key={i} cx={50 + ((i * 37) % 300)} cy={45 + ((i * 53) % 210)} r="1.5" fill={i % 7 === 0 ? 'rgba(124,92,255,0.5)' : 'rgba(59,130,246,0.2)'} />)}
            </svg>
          </div>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="border-t border-violet-300/10 bg-[#030716] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-4 flex items-center gap-2"><MiraiLogo /><span className="text-sm text-[#F6F4EA]">Mirai DoE Engine</span></div>
            <p className="max-w-md text-xs leading-relaxed text-[#5A6B89]">Data-to-decision for industrial R&amp;D teams optimizing complex systems under budget, time, and uncertainty constraints.</p>
          </div>
          <div className="flex gap-5 text-xs text-[#5A6B89]">
            <a href="#workflow" onClick={(event) => { event.preventDefault(); scrollToHash('#workflow') }} className="hover:text-[#9BA8C0]">Workflow</a>
            <a href="#proof" onClick={(event) => { event.preventDefault(); scrollToHash('#proof') }} className="hover:text-[#9BA8C0]">Proof</a>
            <a href="#cta" onClick={(event) => { event.preventDefault(); scrollToHash('#cta') }} className="hover:text-[#9BA8C0]">Contact</a>
          </div>
        </div>
        <div className="const-divider my-6" />
        <div className="flex items-center justify-between text-[10px] text-[#5A6B89]">
          <span>&copy; 2026 Mirai DoE Engine. All rights reserved.</span>
          <span className="font-mono uppercase tracking-[0.08em]">Industrial R&amp;D optimization</span>
        </div>
      </div>
    </footer>
  )
}

export function LandingPage() {
  return (
    <main className="min-h-[100dvh] bg-[#030716] text-[#F6F4EA]">
      <Navbar />
      <Hero />
      <Problem />
      <Workflow />
      <VirtualNavigator />
      <Proof />
      <TestPlans />
      <Industries />
      <Cta />
      <Footer />
    </main>
  )
}
