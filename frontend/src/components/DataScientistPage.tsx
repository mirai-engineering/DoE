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

export function DataScientistPage({ schema }: { schema: ProjectSchema }) {
  const [messages, setMessages] = useState<ChatItem[]>([])
  const [draft, setDraft] = useState('')
  const [events, setEvents] = useState<DataScientistEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
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
      <div className="grid gap-5 xl:grid-cols-[22rem_minmax(0,1fr)]">
        <aside className="space-y-4">
          <div className="rounded-xl border border-[#263654] bg-[#0D1730] p-5 shadow-2xl shadow-black/20">
            <p className="font-mono text-xs font-bold uppercase tracking-[0.22em] text-slate-300">Suggested investigations</p>
            <div className="mt-5 space-y-3">
              {starters.map((starter, index) => (
                <button
                  key={starter}
                  type="button"
                  onClick={() => void submitQuestion(starter)}
                  disabled={loading}
                  className={`group w-full rounded-lg border px-4 py-4 text-left text-sm font-semibold leading-6 transition disabled:cursor-not-allowed disabled:opacity-50 ${index === 2 ? 'border-[#7C5CFF]/60 bg-[#201F55]/80 text-white shadow-lg shadow-[#7C5CFF]/10' : 'border-[#263654] bg-[#0F1B35] text-[#D8E3F8] hover:border-[#74C7F5]/50 hover:bg-[#132344]'}`}
                >
                  {starter}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-[#263654] bg-[#0D1730] px-4 py-3 font-mono text-sm font-semibold tracking-[0.12em] text-[#7C5CFF]">
            <span className="mr-3 inline-block h-2.5 w-2.5 rounded-full bg-[#7C5CFF]" />
            Project-scoped
          </div>
          <div className="rounded-lg border border-[#263654] bg-[#0D1730] px-4 py-3 font-mono text-sm font-semibold tracking-[0.12em] text-[#5DA8FF]">
            <span className="mr-3 inline-block h-2.5 w-2.5 rounded-full bg-[#5DA8FF]" />
            Read-only analysis
          </div>
          <div className="rounded-lg border border-[#263654] bg-[#0D1730] px-4 py-3 font-mono text-sm font-semibold tracking-[0.12em] text-[#CDBF8A]">
            <span className="mr-3 inline-block h-2.5 w-2.5 rounded-full bg-[#CDBF8A]" />
            Grounded in project artifacts
          </div>
        </aside>

        <section className="overflow-hidden rounded-xl border border-[#263654] bg-[#0B1220] shadow-2xl shadow-black/25">
          <div className="flex flex-col gap-4 border-b border-[#263654] bg-[#0D1730] px-6 py-5 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#251F63] shadow-lg shadow-[#7C5CFF]/20">
                <span className="h-3 w-3 rounded-full bg-[#7C5CFF]" />
              </div>
              <div>
                <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">Mirai Data Scientist</h2>
                <p className="font-mono text-sm font-semibold tracking-[0.14em] text-[#74C7F5]">Active · Project-scoped</p>
              </div>
            </div>
            <div className="rounded-full border border-[#415276] px-4 py-1.5 font-mono text-xs font-semibold tracking-[0.16em] text-slate-400">
              {schema.display_name ? 'PROJECT' : 'ID'}
            </div>
          </div>

          {error && <div className="m-6"><Alert tone={error === 'Request cancelled.' ? 'warning' : 'error'} title="Data Scientist" messages={[error]} /></div>}

          <div className="flex min-h-[34rem] flex-col">
            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
              {messages.length === 0 ? (
                <div className="rounded-xl border border-[#263654] bg-[#101D3A] p-8 text-center">
                  <p className="text-lg font-semibold text-white">Ask a scoped project question</p>
                  <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-300">Choose a suggested investigation or ask directly. Answers stay inside the active project and cite only safe, sanitized context.</p>
                </div>
              ) : (
                messages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[82%] rounded-xl px-5 py-4 text-base leading-7 shadow-xl ${message.role === 'user' ? 'border border-[#7C5CFF]/45 bg-[#26245F] text-white shadow-[#7C5CFF]/10' : 'border border-[#263654] bg-[#101D3A] text-[#D8E3F8] shadow-black/20'}`}>
                      {message.role === 'assistant' && (
                        <div className="mb-3 flex flex-wrap gap-2">
                          <span className="rounded-full border border-[#74C7F5]/35 bg-[#12304A] px-3 py-1 font-mono text-[0.65rem] font-bold uppercase tracking-[0.16em] text-[#74C7F5]">Cited from project</span>
                          <span className="rounded-full border border-[#7C5CFF]/35 bg-[#201F55] px-3 py-1 font-mono text-[0.65rem] font-bold uppercase tracking-[0.16em] text-[#9E8CFF]">Read-only tools</span>
                        </div>
                      )}
                      <p className="whitespace-pre-wrap">{message.content}</p>
                      {message.stopReason && <p className="mt-3 font-mono text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Stop: {message.stopReason.replace(/_/g, ' ')}</p>}
                    </div>
                  </div>
                ))
              )}
              {loading && <div className="rounded-xl border border-[#263654] bg-[#101D3A] p-4 text-sm text-slate-300">Checking scoped project tools…</div>}
            </div>

            <form onSubmit={handleSubmit} className="border-t border-[#263654] bg-[#0D1730] px-5 py-4">
              <div className="flex flex-col gap-3 rounded-lg border border-[#2D3F63] bg-[#101D3A] p-3 md:flex-row md:items-end">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={2}
                  maxLength={4000}
                  placeholder="Ask about data, preprocessing, or model quality…"
                  className="min-h-[3rem] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-base text-slate-100 outline-none placeholder:text-slate-500 focus:ring-0"
                />
                <div className="flex items-center gap-2">
                  <span className="hidden font-mono text-xs font-semibold uppercase tracking-[0.14em] text-[#7C5CFF] md:inline">Agent ready</span>
                  <button type="submit" disabled={loading || !draft.trim()} className="rounded-md bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-[#2F6BFF]/20 disabled:cursor-not-allowed disabled:opacity-50">Ask</button>
                  {loading && <button type="button" onClick={cancelRequest} className="rounded-md border border-[#74C7F5]/30 bg-[#0D1B2D] px-4 py-3 text-sm font-semibold text-[#BDEAFF]">Cancel</button>}
                </div>
              </div>
            </form>

            <div className="border-t border-[#263654] bg-[#0D1730] px-6 py-5">
              <p className="font-mono text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Tool activity</p>
              <div className="mt-4 space-y-2">
                {events.length === 0 ? (
                  <p className="text-sm text-slate-500">No tool activity yet.</p>
                ) : (
                  events.map((event, index) => (
                    <div key={`${event.label}-${index}`} className="grid gap-2 text-sm text-slate-300 md:grid-cols-[minmax(0,1fr)_auto]">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#7C5CFF]" />
                        <span className="truncate text-slate-100">{event.label}</span>
                      </div>
                      <span className="font-mono text-xs uppercase tracking-[0.12em] text-slate-500">{event.tool_name ?? event.type}</span>
                      {event.detail && <p className="md:col-span-2 ml-4 text-xs leading-5 text-slate-500">{event.detail}</p>}
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
