import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react'
import { SignInButton } from '@clerk/clerk-react'
import batteriesImage from '../../assets/batteries.png'
import coverageMapImage from '../../assets/coverage-map.png'
import catImage from '../../assets/CAT.png'
import miningImage from '../../assets/mining.png'
import materialsImage from '../../assets/materials.png'
import processImage from '../../assets/process.png'
import residualPlotImage from '../../assets/residual-plot.png'

const CONTACT_EMAIL = 'contact@mirai-engineeirng.com'

const NAV_ITEMS = [
  { label: 'Knowledge', href: '#engineering-knowledge' },
  { label: 'Workflow', href: '#workflow' },
  { label: 'Data Scientist', href: '#data-scientist' },
  { label: 'Proof', href: '#proof' },
  { label: 'Decisions', href: '#test-plans' },
]

const PROCESS_STAGES = [
  { number: '1', title: 'Maintenance', desc: 'Unify work orders, inspection notes, failure history, and sensor exports to decide which assets need attention first.', meta: 'Asset priority' },
  { number: '2', title: 'Operating Windows', desc: 'Connect requirements, plant records, and process data to find safer, more efficient settings.', meta: 'Recommended settings' },
  { number: '3', title: 'Constraint Conflicts', desc: 'Surface mismatched limits across PDFs, spreadsheets, and engineering notes before they become operational risk.', meta: 'Review queue' },
  { number: '4', title: 'Downtime Risk', desc: 'Learn from fragmented historical signals to anticipate where intervention is most likely to pay off.', meta: 'Decision support' },
]

const PRODUCT_STAGES = [
  { number: '1', title: 'Experimental Data', desc: 'Capture formulations, process settings, test conditions, and measured outcomes in one trusted table.', meta: 'Rows / variables / outcomes' },
  { number: '2', title: 'Validated Models', desc: 'Train surrogate models that show which variables drive performance, cost, and technical risk.', meta: 'Quality checked' },
  { number: '3', title: 'What-Ifs', desc: 'Compare virtual configurations before running another build, batch, or lab experiment.', meta: '320 candidates' },
  { number: '4', title: 'Recommendations', desc: 'Rank the next physical test with expected trade-offs, uncertainty, and evidence attached.', meta: '5 ranked actions' },
]

const STORY_STAGES = [
  {
    num: '01', label: 'Tabular Experiment Data',
    headline: 'Product and process R&D already produces the data Mirai needs: rows of experiments, columns of settings, and measured outcomes.',
    body: 'Recipes, operating conditions, material choices, batch records, and test results are brought together into a clean tabular view engineers can trust.',
    metrics: ['Inputs mapped', 'Outcomes linked', 'Context preserved'],
    bg: '/assets/lab-scene.png',
  },
  {
    num: '02', label: 'Validated Surrogate Model',
    headline: 'Mirai learns the relationship between controllable variables and product or process performance.',
    body: 'The platform trains validated surrogate models on your table, checks data quality, and shows where predictions are reliable versus uncertain.',
    metrics: ['Design space learned', 'Diagnostics included', 'Uncertainty visible'],
    bg: '/assets/batteries-all.png',
  },
  {
    num: '03', label: 'Virtual What-Ifs',
    headline: 'Teams can compare thousands of possible settings before spending budget on the next physical run.',
    body: 'Mirai ranks candidates across competing objectives like yield, cost, durability, quality, and performance — using the same tabular contract across domains.',
    metrics: ['Many candidates', 'Trade-offs ranked', 'Risk flagged'],
    bg: '/assets/perfect-battery.png',
  },
  {
    num: '04', label: 'Decision-Ready Plan',
    headline: 'The result is not a dashboard. It is a ranked next-experiment plan with evidence and trade-offs attached.',
    body: 'Engineers inspect the recommendation, understand why it is suggested, and take a defensible run plan back to the lab or production floor.',
    metrics: ['Next run selected', 'Objectives balanced', 'Exportable plan'],
    bg: '/assets/optimization-dash.png',
  },
]

const PROMPTS = [
  'Which requirements constrain this asset?',
  'Where is the pressure limit documented?',
  'Which files disagree about operating limits?',
  'What maintenance events happened before downtime?',
  'Which inspections mention recurring failures?',
  'Can this be turned into a structured table?',
]

const ACTIVITY_LOG = [
  { action: 'Scanned requirement documents', meta: '18 files' },
  { action: 'Matched asset identifiers', meta: '42 aliases resolved' },
  { action: 'Found conflicting limits', meta: '3 items flagged' },
  { action: 'Linked maintenance history', meta: '126 events' },
  { action: 'Prepared structured table', meta: 'Review required' },
]

const PILLARS = [
  { mark: 'I', label: 'Ingest & Structure', desc: 'Connect engineering sources into structured, ML-ready data with schema, units, provenance, and context preserved.' },
  { mark: 'V', label: 'Validate & Diagnose', desc: 'Cross-validation, residual analysis, calibration, and coverage maps are first-class outputs.' },
  { mark: 'R', label: 'Recommend with Trust', desc: 'Predictions include confidence intervals and extrapolation risk flags on the decision space.' },
]

const CANDIDATES = [
  { id: 'C-017', perf: '+12.6%', dur: '+8.7%', cost: '-4.1%', best: true },
  { id: 'C-023', perf: '+5.4%', dur: '+12.2%', cost: '+2.3%', best: false },
  { id: 'C-008', perf: '+9.5%', dur: '-6.0%', cost: '+12.0%', best: false },
  { id: 'C-031', perf: '+2.3%', dur: '+14.0%', cost: '-3.0%', best: false },
  { id: 'C-042', perf: '+6.7%', dur: '-2.0%', cost: '+0.8%', best: false },
]

const INDUSTRIES = [
  { title: 'Batteries', objectives: 'Capacity retention, fast-charge, safety margins, cost', detail: 'Balance formation protocols, material formulations, and cycle-life targets under sparse experimental budgets.', image: batteriesImage },
  { title: 'Materials', objectives: 'Strength, fatigue, corrosion, manufacturability', detail: 'Connect composition and processing variables to measured properties with traceable surrogate models.', image: materialsImage },
  { title: 'Electrolyzers', objectives: 'Efficiency, lifetime, operating window, stack cost', detail: 'Optimize operating conditions while keeping durability and degradation risks visible.', image: processImage },
  { title: 'Advanced manufacturing', objectives: 'Yield, cycle time, defects, energy use', detail: 'Rank parameter sets for production experiments where downtime and scrap are expensive.', image: miningImage },
]

const scatterPoints = Array.from({ length: 40 }, (_, i) => ({
  x: 5 + (i / 39) * 110,
  y: 95 - (i / 39) * 90 + (((i * 17) % 9) - 4) * 1.6,
}))
function scrollToHash(hash: string) {
  document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth' })
}

function showDemoContactMessage(event: MouseEvent<HTMLElement>) {
  event.preventDefault()
  window.alert(`To request a demo, please write us at ${CONTACT_EMAIL}.`)
}

function Eyebrow({ children }: { children: string }) {
  return <p className="mb-5 inline-flex rounded-full border border-[#63D7FF]/30 bg-[#63D7FF]/10 px-3 py-1.5 font-mono text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-[#8DEBFF] shadow-[0_0_18px_rgba(99,215,255,0.10)]">{children}</p>
}

function Meta({ children, className = '' }: { children: string; className?: string }) {
  return <p className={`font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-[#AEBBDD] ${className}`}>{children}</p>
}

function MiraiLogo({ className = '' }: { className?: string }) {
  return <img src="/assets/mirai-mark.png" alt="Mirai" className={`h-9 w-9 rounded-lg border border-cyan-300/20 bg-[#050914] object-cover ring-1 ring-white/10 ${className}`} />
}

function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleNav = useCallback((event: MouseEvent<HTMLAnchorElement>) => {
    const href = event.currentTarget.getAttribute('href')
    if (!href?.startsWith('#')) return
    event.preventDefault()
    scrollToHash(href)
    setMobileOpen(false)
  }, [])

  return (
    <header className={`fixed left-0 right-0 top-0 z-50 transition-all duration-300 ${scrolled ? 'border-b border-cyan-300/15 bg-[#030716]/85 backdrop-blur-lg' : 'bg-transparent'}`}>
      <nav className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-6">
        <a href="#" onClick={handleNav} className="flex items-center gap-3" aria-label="Mirai home">
          <MiraiLogo />
          <span className="text-base font-semibold tracking-tight text-[#F6F4EA]">Mirai</span>
        </a>

        <div className="hidden items-center gap-8 md:flex">
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href} onClick={handleNav} className="text-sm text-[#C5D0E6] transition-colors duration-200 hover:text-[#F6F4EA]">{item.label}</a>
          ))}
          <a href={`mailto:${CONTACT_EMAIL}?subject=Mirai%20%E2%80%94%20Demo%20Request`} onClick={showDemoContactMessage} className="inline-flex h-9 items-center rounded-full bg-[#63D7FF] px-5 text-xs font-semibold tracking-wide text-[#030716] shadow-[0_0_22px_rgba(99,215,255,0.22)] transition-all duration-200 hover:bg-[#8DEBFF]">Request a demo</a>
        </div>

        <button onClick={() => setMobileOpen((open) => !open)} className="flex flex-col gap-1.5 p-2 md:hidden" aria-label="Toggle menu" aria-expanded={mobileOpen}>
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? 'translate-y-[3px] rotate-45' : ''}`} />
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? 'opacity-0' : ''}`} />
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? '-translate-y-[3px] -rotate-45' : ''}`} />
        </button>
      </nav>

      {mobileOpen && (
        <div className="border-t border-cyan-300/15 bg-[#030716]/95 px-6 py-6 backdrop-blur-lg md:hidden">
          <div className="flex flex-col gap-3">
            {NAV_ITEMS.map((item) => (
              <a key={item.href} href={item.href} onClick={handleNav} className="text-sm text-[#C5D0E6] transition-colors hover:text-[#F6F4EA]">{item.label}</a>
            ))}
            <a href={`mailto:${CONTACT_EMAIL}?subject=Mirai%20%E2%80%94%20Demo%20Request`} onClick={showDemoContactMessage} className="mt-2 inline-flex h-9 items-center justify-center rounded-full bg-[#63D7FF] px-5 text-xs font-semibold tracking-wide text-[#030716] shadow-[0_0_22px_rgba(99,215,255,0.22)]">Request a demo</a>
          </div>
        </div>
      )}
    </header>
  )
}

function Hero() {
  return (
    <section className="relative min-h-[100dvh] overflow-hidden bg-[#030716]">
      <div className="absolute inset-0 lg:left-[32%]">
        <img src="/assets/hero.png" alt="" className="h-full w-full object-cover object-[82%_center] opacity-90 lg:opacity-100" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#030716] via-[#030716]/68 to-transparent lg:via-[#030716]/28" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#030716]/35 via-transparent to-[#030716]/10" />
      </div>
      <div className="pointer-events-none absolute -right-1/4 top-1/3 h-1/2 w-1/2 rounded-full bg-[#63D7FF]/12 blur-[120px]" />
      <div className="pointer-events-none absolute -bottom-1/4 left-0 h-1/2 w-1/2 rounded-full bg-[#63D7FF]/10 blur-[100px]" />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-[1400px] flex-col items-start justify-center px-6 pb-20 pt-24 lg:flex-row lg:items-center lg:gap-12">
        <div className="relative z-10 w-full max-w-[540px] shrink-0 animate-fade-in-up">
          <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.18em] text-[#63D7FF] drop-shadow-[0_0_18px_rgba(99,215,255,0.35)]">Engineering knowledge to decision support</p>
          <h1 className="text-4xl font-semibold leading-[1.06] tracking-tight sm:text-5xl lg:text-[3.25rem]">
            <span className="text-[#F6F4EA]">Model better products and processes</span><br />
            <span className="bg-gradient-to-r from-[#63D7FF] via-[#8DEBFF] to-[#C8F7FF] bg-clip-text text-transparent drop-shadow-[0_0_28px_rgba(99,215,255,0.28)]">before you run them.</span>
          </h1>
          <p className="mt-5 max-w-[520px] text-base leading-relaxed text-[#C5D0E6]">Mirai turns fragmented engineering knowledge — PDFs, reports, spreadsheets, test benches, maintenance records, requirements, and measured outcomes — into <span className="text-[#8DEBFF]">structured engineering data</span>, validated models, and ranked decisions.</p>

          <div className="mt-8 flex flex-wrap gap-3">
            <a href="#cta" onClick={(event) => { event.preventDefault(); scrollToHash('#cta') }} className="inline-flex h-11 items-center rounded-full bg-[#63D7FF] px-7 text-sm font-semibold tracking-wide text-[#030716] shadow-[0_0_26px_rgba(99,215,255,0.24)] transition-all duration-200 hover:bg-[#8DEBFF]">Explore the platform</a>
            <SignInButton mode="modal">
              <button className="inline-flex h-11 items-center rounded-full border border-[#63D7FF]/35 px-7 text-sm font-medium tracking-wide text-[#C5D0E6] transition-all duration-200 hover:border-[#63D7FF]/70 hover:text-[#F6F4EA]">Sign in</button>
            </SignInButton>
          </div>

          <div className="mt-12 grid w-full gap-4 sm:grid-cols-2 lg:w-[min(1080px,calc(100vw-3rem))] lg:grid-cols-4">
            {[
              { icon: '01', label: 'Knowledge', desc: 'The information already exists: requirements, reports, logs, and test results. It is scattered across systems and formats.' },
              { icon: '02', label: 'Structure', desc: 'Your experts know the answers. Mirai helps bring what lives in documents, spreadsheets, and people’s heads into one trusted engineering view.' },
              { icon: '03', label: 'Learn', desc: 'Teams should not spend hours hunting for information. They should see patterns, risks, constraints, and opportunities.' },
              { icon: '04', label: 'Decide', desc: 'The next project should not start from zero. Every recommendation should build on what you already know.' },
            ].map((feature, index) => (
              <div key={feature.label} className="relative rounded-2xl border border-[#63D7FF]/25 bg-[#09152F]/90 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.06),0_0_32px_rgba(99,215,255,0.05)] backdrop-blur-sm">
                {index < 3 && <div className="absolute -right-3 top-1/2 hidden h-px w-6 bg-gradient-to-r from-[#63D7FF]/70 to-transparent md:block" />}
                <span className="font-mono text-xs tracking-[0.18em] text-[#63D7FF] drop-shadow-[0_0_14px_rgba(99,215,255,0.65)]">{feature.icon}</span>
                <p className="mt-3 text-lg font-semibold leading-tight text-[#DDF8FF]">{feature.label}</p>
                <p className="mt-3 text-sm leading-relaxed text-[#D6DEF0]">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="hidden lg:block lg:flex-1" />
      </div>
    </section>
  )
}

function ProblemKnowledge() {
  const files = ['Requirements.pdf', 'Maintenance_Log_v4.xlsx', 'Inspection_Report_FINAL.docx', 'Operations_Notes.docx', 'Asset_History.pdf', 'Test_Bench_Output.csv']

  return (
    <section id="engineering-knowledge" className="relative border-t border-[#55D5FF]/10 bg-[radial-gradient(circle_at_70%_20%,rgba(34,72,102,0.18),transparent_42%),linear-gradient(180deg,#0B1118_0%,#070D14_100%)] py-24">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="grid items-center gap-14 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <Eyebrow>Problem 1</Eyebrow>
            <h2 className="text-4xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-5xl">Your engineering knowledge is trapped.</h2>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-[#D6DEF0]">Your company has already created the knowledge. But when it lives across documents, spreadsheets, reports, sensor exports, and people’s heads, every decision starts with a search.</p>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-[#AEBBDD]">Mirai turns that scattered context into a structured engineering view that teams can inspect, connect, and trust.</p>
          </div>

          <div className="relative min-h-[420px] overflow-hidden rounded-3xl border border-[#55D5FF]/12 bg-[#08121E] p-6 shadow-[0_0_40px_rgba(34,72,102,0.10)]">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(34,72,102,0.18),transparent_30%),radial-gradient(circle_at_80%_90%,rgba(85,213,255,0.08),transparent_32%)]" />
            {files.map((file, index) => (
              <div key={file} className="absolute rounded-xl border border-cyan-300/20 bg-[#0D1D3D]/95 px-4 py-3 shadow-[0_16px_40px_rgba(0,0,0,0.24)]" style={{ left: `${8 + ((index * 23) % 58)}%`, top: `${12 + ((index * 17) % 62)}%`, transform: `rotate(${[-6, 4, -3, 7, -5, 3][index]}deg)` }}>
                <Meta className="text-[#63D7FF]">Source</Meta>
                <p className="mt-1 whitespace-nowrap text-sm font-semibold text-[#F6F4EA]">{file}</p>
              </div>
            ))}
            <div className="absolute bottom-6 left-6 right-6 rounded-2xl border border-blue-300/20 bg-[#030716]/85 p-5 backdrop-blur-md">
              <p className="text-xl font-semibold text-[#F6F4EA]">Same project. Six formats. No shared structure.</p>
              <p className="mt-2 text-sm leading-relaxed text-[#C5D0E6]">This is where Mirai starts — before models, before optimization, before recommendations.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function ProblemDecisions() {
  return (
    <section className="relative border-t border-[#55D5FF]/10 bg-[radial-gradient(circle_at_70%_20%,rgba(34,72,102,0.18),transparent_42%),linear-gradient(180deg,#0B1118_0%,#070D14_100%)] py-24">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-3xl text-center">
          <Eyebrow>Problem 2</Eyebrow>
          <h2 className="text-4xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-5xl">Once the data is organized, the next decision is still uncertain.</h2>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-[#D6DEF0]">Which asset should be maintained first? Which process change is worth testing? Which operating point is safest? Which battery formulation should move forward?</p>
        </div>

        <div className="mt-14 grid items-stretch gap-6 lg:grid-cols-[0.95fr_1fr]">
          <div className="grid gap-5 lg:grid-rows-2">
            {[
              {
                num: '01',
                title: 'Process Engineering',
                lead: 'Plant and process data is finally connected. Now engineers need predictive answers:',
                questions: ['How should we run the plant to maximize output?', 'When should we stop for maintenance before failure or quality drift?', 'Which operating settings improve yield without violating constraints?'],
                consequence: 'These are classical prediction and optimization problems — but the cost of a wrong answer is downtime, scrap, and lost capacity.',
              },
              {
                num: '02',
                title: 'Product Engineering',
                lead: 'Experimental results are finally organized. Now R&D must choose the next configuration:',
                questions: ['Which formulation maximizes power while reducing cost?', 'How do we improve the product with the fewest physical iterations?', 'Which candidate should be tested next to reduce uncertainty fastest?'],
                consequence: 'The design space is too large for trial and error. Teams need to rank trade-offs before committing budget to another build.',
              },
            ].map((card) => (
              <div key={card.title} className="group relative flex min-h-[200px] flex-col justify-between overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#09152F] p-6 transition-all duration-300 hover:-translate-y-0.5 hover:border-cyan-300/35 hover:bg-[#0B1938] lg:min-h-0">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#63D7FF]/45 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                <div>
                  <span className="font-mono text-[11px] font-semibold tracking-[0.16em] text-[#63D7FF]">{card.num}</span>
                  <h3 className="mt-4 text-xl font-semibold text-[#F6F4EA]">{card.title}</h3>
                  <p className="mt-3 max-w-[34rem] text-sm leading-relaxed text-[#E3EAF4]">{card.lead}</p>
                  <ul className="mt-3 space-y-1.5 text-sm leading-relaxed text-[#D6DEF0]">
                    {card.questions.map((question) => (
                      <li key={question} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-[#63D7FF]/70" />{question}</li>
                    ))}
                  </ul>
                </div>
                <p className="mt-5 border-t border-cyan-300/10 pt-4 text-sm leading-relaxed text-[#B7C2D0]">{card.consequence}</p>
              </div>
            ))}
          </div>

          <div className="w-fit self-center justify-self-center overflow-hidden rounded-2xl border border-blue-300/15 bg-[#020817] p-5 shadow-[0_0_28px_rgba(59,130,246,0.08)]">
            <img src="/assets/problem-diagram.png" alt="Fragmented engineering sources unified into a traceable decision dataset" className="h-[420px] w-auto max-w-full rounded-xl object-contain object-center opacity-90" />
          </div>
        </div>
      </div>
    </section>
  )
}


function StageGrid({ stages }: { stages: typeof PROCESS_STAGES }) {
  return (
    <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {stages.map((stage, index) => (
        <div key={stage.number} className="relative animate-fade-in-up" style={{ animationDelay: `${index * 60}ms` }}>
          {index < stages.length - 1 && <div className="absolute left-full top-1/2 hidden h-px w-3 -translate-y-1/2 bg-gradient-to-r from-[#63D7FF]/25 to-blue-400/5 lg:block" />}
          <div className="relative z-10 flex h-full min-h-[250px] flex-col rounded-xl border border-cyan-300/15 bg-[#0A1630] p-4">
            <div className="mb-4 flex min-h-[32px] items-center gap-2">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#63D7FF]/15 text-[11px] font-semibold text-[#63D7FF]">{stage.number}</span>
              <p className="text-base font-semibold leading-tight text-[#F6F4EA]">{stage.title}</p>
            </div>
            <p className="text-sm leading-relaxed text-[#D6DEF0]">{stage.desc}</p>
            <div className="mt-auto rounded-lg border border-cyan-300/15 bg-[#0D1D3D]/70 px-3 py-3">
              <div className="flex min-h-[30px] items-center justify-between gap-3">
                <span className="font-mono text-[10px] uppercase leading-relaxed tracking-[0.08em] text-[#AEBBDD]">{stage.meta}</span>
                <div className="h-2 w-2 shrink-0 rounded-full bg-[#63D7FF]/60" />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function Workflow() {
  return (
    <section id="workflow" className="relative border-t border-[#55D5FF]/20 bg-[radial-gradient(circle_at_50%_0%,rgba(28,126,177,0.16),transparent_45%),linear-gradient(180deg,#03131F_0%,#020B14_100%)] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-[46rem] text-center">
          <Eyebrow>Solution 2</Eyebrow>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">From engineering knowledge to ranked decisions.</h2>
          <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-[#E3EAF4]">Once engineering knowledge is connected, Mirai helps teams turn predictive uncertainty into ranked, evidence-based operating and design decisions.</p>
        </div>
        <div className="mt-12 rounded-2xl border border-cyan-300/15 bg-[#071126]/60 p-5">
          <Meta className="text-[#63D7FF]">Example 1 — Process Engineering</Meta>
          <h3 className="mt-2 text-2xl font-semibold tracking-tight text-[#F6F4EA]">Mirai helps rank operating changes, maintenance timing, and process settings.</h3>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[#C5D0E6]">Once knowledge is connected, teams can compare throughput, safety, constraint, and downtime decisions with the evidence attached.</p>
          <StageGrid stages={PROCESS_STAGES} />
        </div>
        <div className="mt-6 rounded-2xl border border-cyan-300/15 bg-[#071126]/60 p-5">
          <Meta className="text-[#63D7FF]">Example 2 — Product Engineering</Meta>
          <h3 className="mt-2 text-2xl font-semibold tracking-tight text-[#F6F4EA]">Mirai helps rank product configurations before another physical iteration.</h3>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[#C5D0E6]">The same decision workflow carries through product R&amp;D: validated models, virtual what-ifs, and ranked trade-offs across performance, cost, and uncertainty.</p>
          <StageGrid stages={PRODUCT_STAGES} />
        </div>
      </div>
    </section>
  )
}

function ExperimentNavigator() {
  const sectionRef = useRef<HTMLDivElement>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const el = sectionRef.current
    if (!el) return
    const onScroll = () => {
      const rect = el.getBoundingClientRect()
      const total = el.offsetHeight - window.innerHeight
      setProgress(total <= 0 ? 0.5 : Math.max(0, Math.min(1, -rect.top / total)))
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const frameCount = STORY_STAGES.length + 1
  const frameIdx = Math.min(frameCount - 1, Math.floor(progress * frameCount))
  const isIntroFrame = frameIdx === 0
  const stageIdx = Math.max(0, frameIdx - 1)
  const stage = STORY_STAGES[stageIdx]

  return (
    <section id="experiment-navigator" ref={sectionRef} className="relative border-t border-cyan-300/15" style={{ height: '500vh' }}>
      <div className="sticky top-0 h-[100dvh] w-full overflow-hidden bg-[#010412]">
        {STORY_STAGES.map((story, index) => (
          <div key={story.num} className={`absolute inset-0 transition-opacity duration-700 ${!isIntroFrame && stageIdx === index ? 'opacity-100' : 'pointer-events-none opacity-0'}`}>
            <img src={story.bg} alt="" className="h-full w-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-r from-[#030716]/90 via-[#030716]/60 to-[#030716]/40" />
            <div className="absolute inset-0 bg-gradient-to-t from-[#030716]/40 to-transparent" />
          </div>
        ))}
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#63D7FF]/30 to-transparent" />

        <div className={`pointer-events-none absolute inset-0 z-20 flex items-center px-6 transition-all duration-700 ${isIntroFrame ? 'translate-y-0 opacity-100' : '-translate-y-8 opacity-0'}`}>
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_78%_45%,rgba(99,215,255,0.16),transparent_30%),linear-gradient(rgba(99,215,255,0.045)_1px,transparent_1px),linear-gradient(90deg,rgba(99,215,255,0.045)_1px,transparent_1px)] bg-[size:auto,64px_64px,64px_64px]" />
          <div className="absolute left-1/2 top-0 h-full w-px bg-gradient-to-b from-transparent via-cyan-300/15 to-transparent" />
          <div className="relative mx-auto grid w-full max-w-[1400px] items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="max-w-4xl border-b border-cyan-300/15 pb-8">
              <div className="mb-8 inline-flex items-center gap-3 rounded-full border border-cyan-300/20 bg-[#071126]/70 px-4 py-2 shadow-[0_0_24px_rgba(99,215,255,0.08)] backdrop-blur">
                <span className="h-1.5 w-1.5 rounded-full bg-[#63D7FF] shadow-[0_0_12px_rgba(99,215,255,0.8)]" />
                <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-[#63D7FF]">Concrete example</span>
              </div>
              <h2 className="text-4xl font-semibold leading-[1.04] tracking-tight text-[#F6F4EA] sm:text-5xl lg:text-6xl">From fragmented data to battery testing.</h2>
              <p className="mt-6 max-w-2xl text-base leading-relaxed text-[#C5D0E6] sm:text-lg">A scroll-through example of how Mirai turns an engineering dataset into a validated model and a ranked next-run plan.</p>
              <div className="mt-8 flex flex-wrap gap-3">
                {['Battery DoE dataset', 'Surrogate model', 'Next-run recommendation'].map((label) => (
                  <span key={label} className="rounded-full border border-cyan-300/15 bg-[#071126]/70 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-[#AFC7DA]">{label}</span>
                ))}
              </div>
            </div>

            <div className="hidden lg:block">
              <div className="relative overflow-hidden rounded-3xl border border-cyan-300/20 bg-[#051026]/80 p-5 shadow-[0_0_42px_rgba(59,130,246,0.12)] backdrop-blur-xl">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#63D7FF]/60 to-transparent" />
                <div className="mb-5 flex items-center justify-between border-b border-cyan-300/10 pb-4">
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#63D7FF]">Example path</p>
                    <p className="mt-1 text-sm font-medium text-[#F6F4EA]">Battery experiment → decision plan</p>
                  </div>
                  <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-[#8DEBFF]">Preview</span>
                </div>
                <div className="space-y-3">
                  {[
                    ['01', 'Fragmented test records', 'Cell metadata, cycling results, and historical runs are normalized.'],
                    ['02', 'Model confidence check', 'Surrogate diagnostics make prediction quality visible before optimization.'],
                    ['03', 'Ranked next run', 'Candidates are scored by expected gain, uncertainty, and practical constraints.'],
                  ].map(([num, title, copy], index) => (
                    <div key={title} className="relative rounded-2xl border border-cyan-300/12 bg-[#081936]/80 p-4">
                      {index < 2 && <div className="absolute -bottom-3 left-8 h-3 w-px bg-cyan-300/25" />}
                      <div className="flex gap-4">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-cyan-300/25 bg-[#63D7FF]/10 font-mono text-[11px] text-[#63D7FF]">{num}</span>
                        <div>
                          <p className="text-sm font-semibold text-[#F6F4EA]">{title}</p>
                          <p className="mt-1 text-xs leading-relaxed text-[#AEBBDD]">{copy}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className={`absolute bottom-8 left-6 right-6 z-20 transition-all duration-700 lg:bottom-0 lg:left-0 lg:top-0 lg:flex lg:w-[440px] lg:max-w-[40vw] lg:flex-col lg:justify-center lg:px-14 ${isIntroFrame ? 'pointer-events-none translate-y-8 opacity-0' : 'translate-y-0 opacity-100'}`}>
          <div className="rounded-2xl border border-white/10 bg-[#030716]/80 p-6 shadow-2xl backdrop-blur-xl lg:p-8">
            <div className="mb-5 flex items-center gap-2">
              {STORY_STAGES.map((item, index) => (
                <div key={item.num} className={`h-[3px] flex-1 rounded-full transition-all duration-500 ${index === stageIdx ? 'bg-[#63D7FF] shadow-[0_0_8px_rgba(99,215,255,0.5)]' : index < stageIdx ? 'bg-[#63D7FF]/50' : 'bg-white/10'}`} />
              ))}
              <span className="ml-1 min-w-[24px] text-right font-mono text-[10px] text-white/30">{stageIdx + 1}/{STORY_STAGES.length}</span>
            </div>
            <p className="mb-2 font-mono text-[12px] font-semibold uppercase tracking-[0.16em] text-[#8DEBFF]">{stage.num} / {stage.label}</p>
            <h3 className="text-[22px] font-semibold leading-snug tracking-tight text-white">{stage.headline}</h3>
            <p className="mt-3 text-[14px] leading-relaxed text-[#C5D0E6]">{stage.body}</p>
            <div className="mt-5 flex flex-wrap gap-3 border-t border-white/10 pt-4">
              {stage.metrics.map((metric) => (
                <div key={metric} className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#63D7FF]" />
                  <span className="font-mono text-[11px] tracking-wide text-[#C5D0E6]">{metric}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {progress < 0.03 && (
          <div className="pointer-events-none absolute bottom-8 left-1/2 z-30 flex -translate-x-1/2 flex-col items-center gap-2">
            <svg width="12" height="20" viewBox="0 0 12 20" className="text-white/30"><rect x="1" y="1" width="10" height="18" rx="5" stroke="currentColor" strokeWidth="1.5" fill="none" /><circle cx="6" cy="7" r="2" fill="currentColor" className="animate-pulse-soft" /></svg>
            <span className="font-mono text-[8px] tracking-[0.2em] text-white/20">SCROLL</span>
          </div>
        )}
      </div>
    </section>
  )
}

function DataScientist() {
  return (
    <section id="data-scientist" className="relative border-t border-[#55D5FF]/20 bg-[radial-gradient(circle_at_50%_0%,rgba(28,126,177,0.16),transparent_45%),linear-gradient(180deg,#03131F_0%,#020B14_100%)] py-20">
      <div className="pointer-events-none absolute left-1/4 right-1/4 top-0 h-px bg-gradient-to-r from-transparent via-[#63D7FF]/25 to-transparent" />
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mb-14 text-center">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#63D7FF]/30 bg-[#63D7FF]/10 px-4 py-1.5 shadow-[0_0_18px_rgba(99,215,255,0.10)]"><span className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8DEBFF]">Solution 1</span></div>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Ask across fragmented engineering knowledge.</h2>
          <p className="mx-auto mt-3 max-w-2xl text-base leading-relaxed text-[#C5D0E6]">Mirai helps teams find requirements, conflicts, maintenance patterns, and source evidence across project files — then turns the result into reviewed structure.</p>
        </div>

        <div className="grid gap-5 lg:grid-cols-[280px_1fr_280px]">
          <div className="space-y-4">
            <div className="rounded-xl border border-cyan-300/15 bg-[#0A1630] p-4">
              <p className="mb-3 font-mono text-[11px] uppercase tracking-wider text-[#C5D0E6]">Suggested investigations</p>
              <div className="space-y-2">
                {PROMPTS.map((prompt, index) => (
                  <div key={prompt} className={`rounded-lg border px-3 py-2.5 text-left text-xs leading-snug transition-all duration-200 ${index === 2 ? 'border-[#63D7FF]/30 bg-[#63D7FF]/10 text-[#F6F4EA]' : 'border-cyan-300/10 bg-[#0D1D3D]/50 text-[#C5D0E6]'}`}>{prompt}</div>
                ))}
              </div>
            </div>
            {[
              ['Project-scoped', 'bg-[#63D7FF]', 'text-[#63D7FF]'],
              ['Source-cited', 'bg-[#3B82F6]', 'text-[#3B82F6]'],
              ['Ready for review', 'bg-[#D8C99B]/60', 'text-[#D8C99B]/80'],
            ].map(([label, dot, text]) => (
              <div key={label} className="flex items-center gap-2 rounded-lg border border-cyan-300/15 bg-[#0A1630] px-3 py-2"><div className={`h-2 w-2 rounded-full ${dot}`} /><span className={`font-mono text-[10px] tracking-wider ${text}`}>{label}</span></div>
            ))}
          </div>

          <div className="overflow-hidden rounded-xl border border-cyan-300/15 bg-[#0A1630] shadow-[0_0_30px_rgba(99,215,255,0.04)]">
            <div className="flex items-center gap-3 border-b border-cyan-300/15 bg-[#0D1D3D]/60 px-5 py-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#63D7FF]/15"><span className="h-2 w-2 rounded-full bg-[#63D7FF]" /></div>
              <div className="flex-1"><p className="text-sm font-medium text-[#F3F7FF]">Mirai Engineering Agent</p><p className="font-mono text-[10px] tracking-wider text-[#8FD3FF]">Active · Project-scoped</p></div>
              <span className="rounded-full border border-cyan-300/15 px-2.5 py-0.5 font-mono text-[8px] tracking-wider text-[#8899BB]">REQ-042</span>
            </div>
            <div className="space-y-5 p-5">
              <div className="flex justify-end"><div className="max-w-[78%] rounded-2xl rounded-br-sm border border-cyan-300/25 bg-[#63D7FF]/20 px-4 py-3"><p className="text-sm text-white">Which files disagree about the pressure limit for this subsystem?</p></div></div>
              <div className="max-w-[88%] rounded-2xl rounded-tl-sm border border-[#111B3A] bg-[#0D1D3D] px-4 py-3.5 shadow-lg">
                <div className="mb-3 flex flex-wrap gap-1.5"><span className="rounded-full border border-cyan-300/20 bg-[#63D7FF]/10 px-2 py-0.5 font-mono text-[8px] tracking-wider text-[#63D7FF]">CITED FROM Requirements.pdf p.324</span><span className="rounded-full border border-cyan-300/20 bg-[#63D7FF]/10 px-2 py-0.5 font-mono text-[8px] tracking-wider text-[#63D7FF]">CITED FROM Operations_Notes.docx</span></div>
                <p className="mb-4 text-sm leading-relaxed text-[#C5D0E6]">Requirement A sets the pressure limit at 12 bar, while operating note 5 lists the same subsystem at 10 bar. Mirai flags the conflict and links both sources for engineering review.</p>
                <div className="mb-3 rounded-lg border border-cyan-300/15 bg-[#63D7FF]/10 p-3">
                  <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-[#63D7FF]/80">Structured findings</p>
                  {[
                    ['Subsystem', 'Pump line P-12', 'text-[#63D7FF]'], ['Conflict', '12 bar vs 10 bar', 'text-[#63D7FF]'], ['Review status', 'Needs approval', 'text-[#3B82F6]'],
                  ].map(([label, value, color]) => <div key={label} className="flex items-center justify-between"><span className="text-xs text-[#8899BB]">{label}</span><span className={`text-xs font-medium ${color}`}>{value}</span></div>)}
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    ['2', 'Source Files', 'text-[#63D7FF]'], ['1', 'Conflict Flag', 'text-[#63D7FF]'], ['Ready', 'Schema Review', 'text-[#3B82F6]'],
                  ].map(([value, label, color]) => <div key={label} className="rounded-lg border border-blue-300/10 bg-[#3B82F6]/5 p-2 text-center"><p className={`text-sm font-medium ${color}`}>{value}</p><p className="mt-0.5 text-[9px] text-[#8899BB]">{label}</p></div>)}
                </div>
              </div>
            </div>
            <div className="border-t border-slate-400/[0.12] px-4 py-3"><div className="flex items-center gap-2 rounded-lg border border-slate-400/[0.16] bg-[#0B1220] px-3 py-2.5"><span className="flex-1 text-xs text-[#6F7A90]">Ask about requirements, limits, assets, or source conflicts...</span><span className="font-mono text-[9px] tracking-wider text-[#63D69A]"><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-[#63D69A]" />READY</span></div></div>
            <div className="border-t border-cyan-300/15 bg-[#0D1D3D]/30 px-5 py-3"><p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-[#8899BB]">Tool activity</p>{ACTIVITY_LOG.map((item, index) => <div key={item.action} className="flex items-center gap-2 text-[10px]"><div className={`h-1 w-1 rounded-full ${index < ACTIVITY_LOG.length - 1 ? 'bg-[#63D7FF]/30' : 'bg-[#63D7FF]'}`} /><span className="text-[#C5D0E6]">{item.action}</span><span className="ml-auto text-[#8899BB]/60">{item.meta}</span></div>)}</div>
          </div>

          <div className="space-y-4">
            <img src="/assets/agent-panel.png" alt="Mirai Data Scientist project evidence panel" className="hidden rounded-xl border border-cyan-300/15 object-cover opacity-90 lg:block" />
            <div className="rounded-xl border border-cyan-300/15 bg-[#0A1630] p-4">
              <p className="mb-3 font-mono text-[11px] uppercase tracking-wider text-[#C5D0E6]">Extraction review</p>
              {[
                ['Requirements', 'PDF + DOCX', 'Conflict'], ['Assets', '42 matched', 'Review'], ['Maintenance Events', '126 linked', 'Ready'], ['Structured Table', '18 fields', 'Draft'],
              ].map(([name, detail, status]) => <div key={name} className="mb-3 flex items-center justify-between last:mb-0"><div><p className="text-xs text-[#C5D0E6]">{name}</p><p className="font-mono text-[10px] text-[#8899BB]">{detail}</p></div><span className="rounded border border-cyan-300/15 px-2 py-0.5 font-mono text-[10px] tracking-wider text-[#63D7FF]">{status}</span></div>)}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function Proof() {
  return (
    <section id="proof" className="relative border-t border-cyan-300/15 bg-[#030716] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-2xl text-center"><Eyebrow>Product proof</Eyebrow><h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Recommendations are only as good as the model behind them.</h2><p className="mt-4 text-sm leading-relaxed text-[#C5D0E6]">Structured data alone is not enough. Mirai prioritizes model quality, traceability, and uncertainty — so decisions are validated, auditable, and repeatable.</p></div>
        <div className="mt-12 grid gap-4 sm:grid-cols-3">{PILLARS.map((pillar) => <div key={pillar.mark} className="rounded-xl border border-cyan-300/20 bg-[#0A1630] p-6"><div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-cyan-300/35 bg-[#63D7FF]/15"><span className="text-sm font-semibold text-[#8DEBFF]">{pillar.mark}</span></div><h3 className="text-base font-semibold text-[#F6F4EA]">{pillar.label}</h3><p className="mt-2 text-sm leading-relaxed text-[#D6DEF0]">{pillar.desc}</p></div>)}</div>
        <div className="mt-8 overflow-hidden rounded-xl border border-cyan-300/20 bg-[#0A1630]"><div className="border-b border-cyan-300/20 px-5 py-3"><Meta className="text-[#AEBBDD]">Model trust & diagnostics</Meta></div><div className="grid gap-4 p-5 sm:grid-cols-3">
          <div className="group overflow-hidden rounded-xl border border-cyan-300/15 bg-[#0D1D3D] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            <div className="relative aspect-[16/9] overflow-hidden bg-[#020817]"><img src="/assets/generated/battery-parity-diagnostics.png" alt="Battery testing parity diagnostics" className="h-full w-full object-cover opacity-90 transition duration-500 group-hover:scale-[1.03]" /><div className="absolute inset-0 bg-gradient-to-t from-[#071126] via-[#071126]/10 to-transparent" /><svg viewBox="0 0 120 100" className="absolute inset-x-6 bottom-5 h-24 opacity-90"><line x1="12" y1="88" x2="108" y2="12" stroke="rgba(124,92,255,0.9)" strokeWidth="1.2" strokeDasharray="4,4" />{scatterPoints.slice(0, 28).map((pt, i) => <circle key={i} cx={pt.x} cy={pt.y} r="2.2" fill="rgba(99,215,255,0.78)" />)}</svg></div>
            <div className="p-4"><Meta className="mb-2 text-[#63D7FF]">Parity plot</Meta><p className="text-sm leading-relaxed text-[#D6DEF0]">Predicted vs. observed battery-test outcomes stay close to the validation diagonal before recommendations are trusted.</p></div>
          </div>
          <div className="group overflow-hidden rounded-xl border border-cyan-300/15 bg-[#0D1D3D] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            <div className="relative aspect-[16/9] overflow-hidden bg-[#071126]"><img src={residualPlotImage} alt="Battery residual plot diagnostics" className="h-full w-full object-contain object-center opacity-95 transition duration-500 group-hover:scale-[1.02]" /></div>
            <div className="p-4"><Meta className="mb-2 text-[#63D7FF]">Residual plot</Meta><p className="text-sm leading-relaxed text-[#D6DEF0]">Residual bands expose systematic drift in charge-cycle measurements before model error turns into wasted lab time.</p></div>
          </div>
          <div className="group overflow-hidden rounded-xl border border-cyan-300/15 bg-[#0D1D3D] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            <div className="relative aspect-[16/9] overflow-hidden bg-[#071126]"><img src={coverageMapImage} alt="Battery design-space coverage map" className="h-full w-full object-contain object-center opacity-95 transition duration-500 group-hover:scale-[1.02]" /></div>
            <div className="p-4"><Meta className="mb-2 text-[#63D7FF]">Coverage map</Meta><p className="text-sm leading-relaxed text-[#D6DEF0]">Coverage maps show where battery formulations are interpolation-safe and where a candidate is extrapolating beyond evidence.</p></div>
          </div>
        </div></div>
        <div className="mx-auto mt-10 max-w-2xl text-center"><div className="const-divider mb-6" /><p className="text-sm italic leading-relaxed text-[#C5D0E6]">Mirai is designed to turn bench logs, experimental tables, and surrogate diagnostics into one quantitative discussion space — so teams can debate evidence instead of anecdotes.</p><p className="mt-3 text-xs text-[#8899BB]">Mirai product principle</p></div>
      </div>
    </section>
  )
}

function TestPlans() {
  return (
    <section id="test-plans" className="relative border-t border-cyan-300/15 bg-[#010412] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="grid items-start gap-10 lg:grid-cols-[0.9fr_1.35fr]">
          <div>
            <Eyebrow>Decision-ready test plans</Eyebrow>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Turn validated models into ranked engineering decisions.</h2>
            <p className="mt-4 text-[15px] leading-relaxed text-[#D6DEF0]">Mirai turns multi-objective trade-offs into clear next steps — what to test, maintain, change, or run next; why it matters; and what you will learn.</p>
            <ul className="mt-6 space-y-3">
              {['Evaluate thousands of feasible virtual candidates before committing lab or operational budget.', 'Rank experiments, maintenance plans, operational recommendations, and engineering decisions.', 'Keep validation and uncertainty visible in the decision workflow.', 'Every plan links back to the source data, transforms, model version, and validation report used.'].map((item) => <li key={item} className="flex items-start gap-2 text-sm leading-relaxed text-[#D6DEF0]"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#63D7FF]" />{item}</li>)}
            </ul>
          </div>
          <div>
            <div className="mb-5 overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#071126] p-3 shadow-[0_0_32px_rgba(99,215,255,0.08)]">
              <div className="h-[300px] overflow-hidden rounded-xl border border-blue-300/10 bg-[#020817]">
                <img src="/assets/run-plan.png" alt="Ranked Mirai run plan" className="h-full w-full object-cover object-[70%_13%] opacity-100" />
              </div>
            </div>
            <div className="overflow-hidden rounded-xl border border-cyan-300/20 bg-[#0A1630]">
              <div className="flex items-center justify-between border-b border-cyan-300/20 px-5 py-3">
                <div className="flex items-center gap-2"><Meta className="text-[#AEBBDD]">Recommended runs</Meta><span className="rounded-full border border-cyan-300/35 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-[#8DEBFF]">5 candidates</span></div>
                <Meta className="hidden text-[#AEBBDD] sm:block">Objectives: Performance, Durability, Cost</Meta>
              </div>
              <div className="grid grid-cols-[1fr_1fr_1fr_1fr_48px] gap-3 border-b border-cyan-300/15 bg-[#0D1D3D]/65 px-5 py-2 font-mono text-[10px] uppercase tracking-[0.08em] text-[#AEBBDD]"><span>Candidate</span><span>Performance</span><span>Durability</span><span>Cost</span><span /></div>
              {CANDIDATES.map((candidate) => <div key={candidate.id} className={`grid grid-cols-[1fr_1fr_1fr_1fr_48px] gap-3 px-5 py-2.5 text-sm ${candidate.best ? 'bg-[#63D7FF]/8' : ''}`}><span className={`font-mono text-[0.75rem] uppercase tracking-[0.08em] ${candidate.best ? 'text-[#63D7FF]' : 'text-[#F6F4EA]'}`}>{candidate.id}{candidate.best && <span className="ml-1.5 text-[9px] text-[#63D7FF]">BEST</span>}</span><span className="text-[#63D7FF]">{candidate.perf}</span><span className={candidate.dur.startsWith('-') ? 'text-[#FF8B72]' : 'text-[#D6DEF0]'}>{candidate.dur}</span><span className="text-[#D6DEF0]">{candidate.cost}</span><span className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#AEBBDD]">Info</span></div>)}
              <div className="flex flex-col gap-3 border-t border-cyan-300/15 px-5 py-3 sm:flex-row sm:items-center sm:justify-between"><Meta className="text-[#AEBBDD]">Model: MLP v2.4 · R²: 0.85 / 0.76 / 0.31 / 0.89</Meta><div className="flex items-center gap-2"><span className="rounded bg-[#0D1D3D] px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em] text-[#63D7FF]">Export CSV</span><span className="rounded bg-[#63D7FF]/10 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em] text-[#8DEBFF]">View details</span></div></div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function Industries() {
  return (
    <section id="industries" className="relative border-t border-cyan-300/15 bg-[#030716] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow>Industries</Eyebrow>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Built for engineering domains where evidence is fragmented and trade-offs are real.</h2>
          <p className="mt-4 text-sm leading-relaxed text-[#D6DEF0]">Start with structured engineering data from documents, systems, and experiments. Expand across teams, projects, and sites.</p>
        </div>
        <div className="mx-auto mt-12 grid max-w-5xl gap-5 md:grid-cols-2">
          {INDUSTRIES.map((industry) => <div key={industry.title} className="group overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#071126] p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] transition-all duration-300 hover:border-cyan-300/35"><div className="aspect-[3/2] overflow-hidden rounded-xl bg-[#030716]"><img src={industry.image} alt={`${industry.title} tabular experiment optimization`} className="h-full w-full object-cover object-center opacity-95 transition duration-500 group-hover:scale-[1.01]" /></div></div>)}
        </div>
      </div>
    </section>
  )
}

function Cta() {
  return (
    <section id="cta" className="relative overflow-hidden border-t border-cyan-300/15 bg-[#010412]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_20%,rgba(99,215,255,0.14),transparent_32%),radial-gradient(circle_at_82%_78%,rgba(59,130,246,0.12),transparent_34%)]" />
      <div className="relative mx-auto max-w-[1400px] px-6 py-20">
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_0.9fr]">
          <div>
            <p className="mb-4 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8DEBFF]">Process and product engineering</p>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-[2.5rem]">Make every decision count.</h2>
            <p className="mt-4 max-w-md text-base leading-relaxed text-[#D6DEF0]">Walk through how Mirai structures engineering knowledge, validates models, and ranks next actions across process and product engineering workflows.</p>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-[#AEBBDD]">Use Mirai to turn documents, historical experiments, maintenance records, and process tables into defensible decisions before the next lab run, plant change, or product iteration.</p>
            <div className="mt-8 flex flex-wrap gap-3"><a href={`mailto:${CONTACT_EMAIL}?subject=Mirai%20%E2%80%94%20Demo%20Request`} onClick={showDemoContactMessage} className="inline-flex h-11 items-center rounded-full bg-[#63D7FF] px-8 text-sm font-semibold tracking-wide text-[#030716] shadow-[0_0_24px_rgba(99,215,255,0.22)] transition-all duration-200 hover:bg-[#8DEBFF]">Request a demo</a><SignInButton mode="modal"><button className="inline-flex h-11 items-center rounded-full border border-cyan-300/30 px-7 text-sm font-medium tracking-wide text-[#D6DEF0] transition-all duration-200 hover:border-[#63D7FF]/50 hover:text-[#F6F4EA]">Sign in to Mirai</button></SignInButton></div>
          </div>
          <div className="w-full max-w-[620px] justify-self-center overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#020817] shadow-[0_0_36px_rgba(99,215,255,0.12)] lg:justify-self-end">
            <div className="aspect-[1694/928] overflow-hidden">
              <img src={catImage} alt="Industrial decision workflow in Mirai" className="h-full w-full object-contain object-center opacity-100" />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  const linkGroups = [
    { title: 'Product', color: 'text-[#3B82F6]', links: [{ label: 'Engineering knowledge', href: '#engineering-knowledge' }, { label: 'How it works', href: '#workflow' }, { label: 'Mirai Data Scientist', href: '#data-scientist' }, { label: 'Validation & uncertainty', href: '#proof' }, { label: 'Ranked decisions', href: '#test-plans' }] },
    { title: 'Industries', color: 'text-[#63D7FF]', links: INDUSTRIES.map((industry) => ({ label: industry.title, href: '#industries' })) },
    { title: 'Company', color: 'text-[#3B82F6]', links: [{ label: 'Security & governance', href: '#cta' }, { label: 'Contact', href: `mailto:${CONTACT_EMAIL}` }] },
  ]
  return (
    <footer className="border-t border-cyan-300/15 bg-[#030716] py-16"><div className="mx-auto max-w-[1400px] px-6"><div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">{linkGroups.map((group) => <div key={group.title}><Meta className={`mb-3 ${group.color}`}>{group.title}</Meta><div className="flex flex-col gap-2">{group.links.map((link) => <a key={link.label} href={link.href} onClick={link.href.startsWith('#') ? (event) => { event.preventDefault(); scrollToHash(link.href) } : undefined} className="text-xs text-[#8899BB] transition-colors hover:text-[#C5D0E6]">{link.label}</a>)}</div></div>)}<div><Meta className="mb-3 text-[#63D7FF]">Get in touch</Meta><div className="flex flex-col gap-2"><a href={`mailto:${CONTACT_EMAIL}?subject=Mirai%20%E2%80%94%20Demo%20Request`} onClick={showDemoContactMessage} className="text-xs text-[#8899BB] transition-colors hover:text-[#C5D0E6]">Request a demo</a><a href={`mailto:${CONTACT_EMAIL}`} className="text-xs text-[#8899BB] transition-colors hover:text-[#C5D0E6]">{CONTACT_EMAIL}</a></div><div className="mt-6 flex items-center gap-3"><MiraiLogo className="opacity-85" /><span className="text-xs font-medium text-[#AEBBDD]">Mirai</span></div></div></div><div className="const-divider mb-4 mt-12" /><div className="flex flex-col gap-2 text-[10px] text-[#8899BB] sm:flex-row sm:items-center sm:justify-between"><span>&copy; 2026 Mirai. All rights reserved.</span><span className="font-mono uppercase tracking-[0.08em]">Data-to-Decision for industrial R&amp;D</span></div></div></footer>
  )
}

export function LandingPage() {
  return (
    <main className="min-h-[100dvh] bg-[#030716] text-[#F6F4EA]">
      <Navbar />
      <Hero />
      <ProblemKnowledge />
      <DataScientist />
      <ProblemDecisions />
      <Workflow />
      <ExperimentNavigator />
      <Proof />
      <TestPlans />
      <Industries />
      <Cta />
      <Footer />
    </main>
  )
}
