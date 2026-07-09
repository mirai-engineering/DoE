import { FormEvent, useMemo, useRef, useState } from 'react'
import type { DataScientistEvent, DataScientistMessage, ProjectSchema } from '../lib/api'
import { askDataScientist } from '../lib/api'
import { Alert } from './ui'

type ChatItem = DataScientistMessage & { stopReason?: string; events?: DataScientistEvent[] }

const starters = [
  'What uploaded data is available for this project?',
  'Summarize the preprocessing status and table profile.',
  'What should I know about model quality and training runs?',
]

const promptChips = [
  { label: 'Available uploaded data', question: starters[0] },
  { label: 'Preprocessing summary', question: starters[1] },
  { label: 'Model quality', question: starters[2] },
]

export function DataScientistPage({ schema }: { schema: ProjectSchema }) {
  const [messages, setMessages] = useState<ChatItem[]>([])
  const [draft, setDraft] = useState('')
  const [events, setEvents] = useState<DataScientistEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [contextCollapsed, setContextCollapsed] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const safeHistory = useMemo(
    () => messages.slice(-8).map((message) => ({ role: message.role, content: message.content })),
    [messages],
  )

  async function submitQuestion(question: string) {
    const trimmed = question.trim()
    if (!trimmed || loading) return
    const nextMessages: ChatItem[] = [...messages, { role: 'user', content: trimmed }]
    setMessages(nextMessages)
    setDraft('')
    setError(null)
    setEvents([])
    setLoading(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const response = await askDataScientist(schema.project_id, trimmed, safeHistory, controller.signal)
      setMessages([...nextMessages, { role: 'assistant', content: response.answer, stopReason: response.stop_reason, events: response.events }])
      setEvents(response.events)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setError('Request cancelled.')
      } else {
        setError(err instanceof Error ? err.message : 'Data Scientist request failed.')
      }
    } finally {
      setLoading(false)
      abortRef.current = null
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void submitQuestion(draft)
  }

  function cancelRequest() {
    abortRef.current?.abort()
  }

  return (
    <div className="space-y-6">
      <div className={`grid gap-5 transition-[grid-template-columns] duration-200 ${contextCollapsed ? 'xl:grid-cols-[2.75rem_minmax(0,1fr)]' : 'xl:grid-cols-[22rem_minmax(0,1fr)]'}`}>
        <aside className={`min-w-0 border-y border-slate-400/[0.10] ${contextCollapsed ? 'py-4' : 'py-5'}`}>
          <div className={`flex items-center ${contextCollapsed ? 'justify-center' : 'justify-between gap-3'}`}>
            {!contextCollapsed && <p className="text-sm font-semibold text-[#B8C2D4]">Assistant context</p>}
            <button
              type="button"
              onClick={() => setContextCollapsed((value) => !value)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-400/[0.12] text-sm font-semibold text-[#9FB0C8] transition hover:border-[#5BA8FF]/30 hover:bg-[#5BA8FF]/10 hover:text-[#F3F7FF]"
              aria-label={contextCollapsed ? 'Show assistant context' : 'Hide assistant context'}
              title={contextCollapsed ? 'Show context' : 'Hide context'}
            >
              {contextCollapsed ? '›' : '‹'}
            </button>
          </div>
          {contextCollapsed ? (
            <div className="mt-5 flex flex-col items-center gap-3 text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-[#7E8AA0] [writing-mode:vertical-rl]">
              <span>Context</span>
            </div>
          ) : <>
          <div className="pt-5">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#7E8AA0]">Suggested investigations</p>
            <div className="mt-5 space-y-3">
              {starters.map((starter, index) => (
                <button
                  key={starter}
                  type="button"
                  onClick={() => void submitQuestion(starter)}
                  disabled={loading}
                  className={`group w-full rounded-md border px-3 py-3 text-left text-sm font-medium leading-6 transition disabled:cursor-not-allowed disabled:opacity-50 ${index === 2 ? 'border-[#5BA8FF]/35 bg-[#5BA8FF]/[0.11] text-[#F3F7FF]' : 'border-slate-400/[0.10] bg-[#101A2C]/60 text-[#D7DEEA] hover:border-[#5BA8FF]/30 hover:bg-[#121F35]/90 hover:text-[#F3F7FF]'}`}
                >
                  {starter}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4 rounded-lg border border-slate-400/[0.12] bg-[#101A2C]/60 px-4 py-3 text-sm font-medium text-[#C9D4E5]">
            <span className="mr-3 inline-block h-2.5 w-2.5 rounded-full bg-[#5BA8FF]/75" />
            Project-scoped
          </div>
          <div className="rounded-lg border border-[#5BA8FF]/20 bg-[#5BA8FF]/10 px-4 py-3 text-sm font-medium text-[#8FCBFF]">
            <span className="mr-3 inline-block h-2.5 w-2.5 rounded-full bg-[#5BA8FF]/75" />
            Read-only analysis
          </div>
          <div className="rounded-lg border border-[#D9C27E]/20 bg-[#D9C27E]/10 px-4 py-3 text-sm font-medium text-[#D8C98F]">
            <span className="mr-3 inline-block h-2.5 w-2.5 rounded-full bg-[#D9C27E]/75" />
            Grounded in project artifacts
          </div>
          </>}
        </aside>

        <section className="overflow-hidden border-y border-slate-400/[0.12] bg-[#0B1220]/72 shadow-[0_24px_80px_rgba(0,0,0,0.18)]">
          <div className="flex flex-col gap-4 border-b border-slate-400/[0.10] bg-[radial-gradient(circle_at_left,rgba(139,92,246,0.12),transparent_280px)] px-6 py-5 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#5BA8FF]/18 bg-[#5BA8FF]/[0.08]">
                <img src="/assets/mirai-mark.png" alt="" className="h-7 w-7 rounded-md object-cover opacity-90" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-xl font-semibold tracking-[-0.03em] text-[#F3F7FF]">Mirai Data Scientist</h2>
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium text-[#63D69A]"><span className="h-1.5 w-1.5 rounded-full bg-[#63D69A]" />Active</span>
                </div>
                <p className="mt-1 text-sm font-medium text-[#B8C2D4]">Project-scoped · Read-only · <span className="text-[#D8C98F]">Grounded</span></p>
              </div>
            </div>
            <div className="rounded-full border border-[#A78BFA]/20 bg-[#8B5CF6]/[0.08] px-4 py-1.5 font-mono text-xs font-semibold tracking-[0.10em] text-[#BDA7FF]">
              {schema.display_name ? 'PROJECT' : 'ID'}
            </div>
          </div>

          {error && <div className="mx-6 mt-5"><Alert tone={error === 'Request cancelled.' ? 'warning' : 'error'} title="Data Scientist" messages={[error]} /></div>}

          <div className="flex min-h-[34rem] flex-col">
            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
              {messages.length === 0 ? (
                <div className="py-3 text-left">
                  <p className="text-[1.35rem] font-semibold tracking-[-0.04em] text-[#F3F7FF]">Ask about this model pipeline</p>
                  <p className="mt-2 max-w-[42rem] text-sm leading-6 text-[#9EAABD]">Mirai can explain uploaded data, preprocessing choices, model quality, and training artifacts.</p>
                </div>
              ) : (
                messages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[82%] rounded-xl px-4 py-3 text-sm leading-6 ${message.role === 'user' ? 'border border-[#5BA8FF]/30 bg-[#5BA8FF]/[0.10] text-[#F3F7FF]' : 'border border-slate-400/[0.12] bg-[#101A2C]/86 text-[#D7DEEA]'}`}>
                      {message.role === 'assistant' && (
                        <div className="mb-3 flex flex-wrap gap-2">
                          <span className="rounded-full border border-[#D9C27E]/20 bg-[#D9C27E]/10 px-3 py-1 text-[0.7rem] font-medium text-[#D8C98F]">Grounded in project artifacts</span>
                          <span className="rounded-full border border-[#5BA8FF]/20 bg-[#5BA8FF]/10 px-3 py-1 text-[0.7rem] font-medium text-[#8FCBFF]">Read-only analysis</span>
                        </div>
                      )}
                      <p className="whitespace-pre-wrap">{message.content}</p>
                      {message.stopReason && <p className="mt-3 text-xs font-medium text-[#7E8AA0]">Stop: {message.stopReason.replace(/_/g, ' ')}</p>}
                    </div>
                  </div>
                ))
              )}
              {loading && <div className="border-l border-[#5BA8FF]/25 pl-4 text-sm text-[#B8C2D4]">Checking scoped project artifacts…</div>}
            </div>

            <div className="px-6 pb-5">
              <div className="mb-4">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#7E8AA0]">Try asking</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {promptChips.map((chip) => (
                    <button
                      key={chip.label}
                      type="button"
                      onClick={() => void submitQuestion(chip.question)}
                      disabled={loading}
                      className="rounded-full border border-slate-400/[0.12] bg-[#5BA8FF]/[0.07] px-3 py-2 text-sm font-medium text-[#C9D4E5] transition hover:border-[#5BA8FF]/30 hover:bg-[#5BA8FF]/[0.12] hover:text-[#F3F7FF] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {chip.label}
                    </button>
                  ))}
                </div>
              </div>

              <form onSubmit={handleSubmit} className="rounded-[14px] border border-slate-400/[0.16] bg-[#0B1220]/95 p-3 shadow-[0_18px_50px_rgba(0,0,0,0.22)]">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={2}
                  maxLength={4000}
                  placeholder="Ask about data, preprocessing, or model quality…"
                  className="min-h-[3rem] w-full resize-none border-0 bg-transparent px-1 py-1 text-[15px] leading-6 text-[#F3F7FF] outline-none placeholder:text-[#6F7A90] focus:ring-0"
                />
                <div className="mt-3 flex flex-col gap-3 border-t border-slate-400/[0.08] pt-3 md:flex-row md:items-center md:justify-between">
                  <p className="text-xs font-medium text-[#7E8AA0]">Project-scoped · Read-only · <span className="text-[#D8C98F]">Grounded</span></p>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-[#63D69A]"><span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-[#63D69A]" />Ready</span>
                    {loading && <button type="button" onClick={cancelRequest} className="rounded-[10px] border border-[#5BA8FF]/30 bg-[#101A2C] px-4 py-2 text-sm font-semibold text-[#8FCBFF]">Cancel</button>}
                    <button type="submit" disabled={loading || !draft.trim()} className="rounded-[10px] border border-white/[0.12] bg-[linear-gradient(180deg,#3478FF,#245FEA)] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_24px_rgba(36,95,234,0.24)] transition hover:bg-[linear-gradient(180deg,#4A8CFF,#2D6BFF)] disabled:cursor-not-allowed disabled:bg-none disabled:bg-[#5BA8FF]/[0.16] disabled:text-white/45 disabled:shadow-none">Ask Mirai</button>
                  </div>
                </div>
              </form>
            </div>

            <div className="border-t border-slate-400/[0.10] px-6 py-5">
              <p className="text-sm font-semibold text-[#F3F7FF]">Evidence trail</p>
              <div className="mt-4 space-y-2">
                {events.length === 0 ? (
                  <p className="text-sm text-[#8A96AA]">No project artifacts queried yet.</p>
                ) : (
                  events.map((event, index) => (
                    <div key={`${event.label}-${index}`} className="grid gap-2 text-sm text-[#B8C2D4] md:grid-cols-[minmax(0,1fr)_auto]">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#D9C27E]" />
                        <span className="truncate text-[#F3F7FF]">{event.label}</span>
                      </div>
                      <span className="text-xs text-[#7E8AA0]">{event.tool_name ?? event.type}</span>
                      {event.detail && <p className="md:col-span-2 ml-4 text-xs leading-5 text-[#7E8AA0]">{event.detail}</p>}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
