import { FormEvent, useMemo, useRef, useState } from 'react'
import type { DataScientistEvent, DataScientistMessage, ProjectSchema } from '../lib/api'
import { askDataScientist } from '../lib/api'
import { Alert, Metadata, PanelHeader, SectionCard } from './ui'

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
      <SectionCard>
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <PanelHeader
            eyebrow="Data Scientist"
            title="Ask scoped questions about this project's data and models"
            description="Mirai uses read-only project tools for uploaded artifacts, preprocessing status, table metadata, training runs, and model quality. Hidden reasoning, storage paths, and tenant identifiers are not shown."
          />
          <div className="grid min-w-[16rem] gap-3 sm:grid-cols-2 lg:grid-cols-1">
            <Metadata label="Project" value={schema.display_name ?? schema.project_id} />
            <Metadata label="Mode" value="Read-only scoped tools" />
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {starters.map((starter) => (
            <button
              key={starter}
              type="button"
              onClick={() => void submitQuestion(starter)}
              disabled={loading}
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-[#60745c] hover:text-[#40513d] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {starter}
            </button>
          ))}
        </div>
      </SectionCard>

      {error && <Alert tone={error === 'Request cancelled.' ? 'warning' : 'error'} title="Data Scientist" messages={[error]} />}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <SectionCard className="flex min-h-[30rem] flex-col">
          <div className="max-h-[32rem] flex-1 space-y-4 overflow-y-auto pr-2">
            {messages.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50/80 p-8 text-center text-sm text-slate-500">
                Ask a question or choose a starter above. Answers stay within the active project.
              </div>
            ) : (
              messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[82%] rounded-3xl px-5 py-4 text-sm leading-6 ${message.role === 'user' ? 'bg-slate-950 text-white' : 'border border-slate-200 bg-white text-slate-700 shadow-sm'}`}>
                    <p className="whitespace-pre-wrap">{message.content}</p>
                    {message.stopReason && <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] opacity-60">Stop: {message.stopReason.replace(/_/g, ' ')}</p>}
                  </div>
                </div>
              ))
            )}
            {loading && <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">Checking scoped project tools…</div>}
          </div>

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-3 rounded-3xl border border-slate-200 bg-slate-50 p-3 sm:flex-row">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={2}
              maxLength={4000}
              placeholder="Ask about uploaded data, preprocessing, or model quality…"
              className="min-h-[3rem] flex-1 resize-none rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-[#60745c] focus:ring-2 focus:ring-[#60745c]/15"
            />
            <div className="flex gap-2 sm:flex-col">
              <button type="submit" disabled={loading || !draft.trim()} className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/15 disabled:cursor-not-allowed disabled:opacity-50">Ask</button>
              {loading && <button type="button" onClick={cancelRequest} className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700">Cancel</button>}
            </div>
          </form>
        </SectionCard>

        <SectionCard>
          <PanelHeader eyebrow="Activity" title="Tool timeline" description="Only safe tool names and sanitized summaries are shown." />
          <div className="mt-5 space-y-3">
            {events.length === 0 ? (
              <p className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">No tool activity yet.</p>
            ) : (
              events.map((event, index) => (
                <div key={`${event.label}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-800">{event.label}</p>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-[0.16em] text-slate-500">{event.type}</span>
                  </div>
                  {event.tool_name && <p className="mt-1 text-xs text-slate-500">Tool: {event.tool_name}</p>}
                  {event.detail && <p className="mt-2 text-xs leading-5 text-slate-500">{event.detail}</p>}
                </div>
              ))
            )}
          </div>
        </SectionCard>
      </div>
    </div>
  )
}
