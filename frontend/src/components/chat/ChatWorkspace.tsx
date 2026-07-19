import { FormEvent, Fragment, KeyboardEvent, type RefObject, useEffect, useMemo, useRef, useState } from 'react'
import type { DataScientistEvent, DataScientistMessage, DataScientistResponse } from '../../lib/api'
import { parseChatMarkdown } from '../../lib/chatPresentation'

export type ChatContextItem = { label: string; value: string }
export type ChatContextArtifact = { label: string; detail?: string }
export type ChatContextAction = { label: string; onClick: () => void }

type ChatItem = DataScientistMessage & { stopReason?: string; events?: DataScientistEvent[] }

export type ChatWorkspaceProps = {
  idPrefix: string
  scopeKey: string
  title: string
  titleLevel?: 'h1' | 'h2'
  contextSummary: string
  groundingSummary: string
  emptyHeading: string
  emptyDescription: string
  suggestions: string[]
  composerLabel: string
  placeholder: string
  loadingLabel?: string
  contextualPrompt?: string
  context: {
    scopeSummary: string
    description?: string
    items: ChatContextItem[]
    artifacts?: ChatContextArtifact[]
    emptyArtifactsCopy?: string
    actions?: ChatContextAction[]
  }
  sendMessage: (message: string, history: DataScientistMessage[], signal: AbortSignal) => Promise<DataScientistResponse>
}

export function ChatWorkspace({ idPrefix, scopeKey, title, titleLevel = 'h1', contextSummary, groundingSummary, emptyHeading, emptyDescription, suggestions, composerLabel, placeholder, loadingLabel = 'Checking project evidence…', contextualPrompt = '', context, sendMessage }: ChatWorkspaceProps) {
  const [messages, setMessages] = useState<ChatItem[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [contextOpen, setContextOpen] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const inFlightRef = useRef(false)
  const generationRef = useRef(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const lastContextualPrompt = useRef('')
  const safeHistory = useMemo(() => messages.slice(-8).map(({ role, content }) => ({ role, content })), [messages])

  useEffect(() => {
    generationRef.current += 1
    abortRef.current?.abort()
    abortRef.current = null
    inFlightRef.current = false
    setMessages([])
    setDraft('')
    setError(null)
    setLoading(false)
    setContextOpen(false)
  }, [scopeKey])

  useEffect(() => () => {
    generationRef.current += 1
    abortRef.current?.abort()
  }, [])

  useEffect(() => {
    if (!contextualPrompt || contextualPrompt === lastContextualPrompt.current) return
    lastContextualPrompt.current = contextualPrompt
    setDraft(contextualPrompt)
  }, [contextualPrompt])

  useEffect(() => { bottomRef.current?.scrollIntoView({ block: 'nearest' }) }, [messages, loading])

  useEffect(() => {
    if (!contextOpen) return
    previousFocusRef.current = document.activeElement as HTMLElement | null
    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButtonRef.current?.focus()
    const handleDrawerKeys = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setContextOpen(false); return }
      if (event.key !== 'Tab') return
      const drawer = closeButtonRef.current?.closest('[role="dialog"]')
      const focusable = drawer ? Array.from(drawer.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')) : []
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', handleDrawerKeys)
    return () => { document.body.style.overflow = originalOverflow; window.removeEventListener('keydown', handleDrawerKeys) }
  }, [contextOpen])

  useEffect(() => {
    if (!contextOpen && previousFocusRef.current) { previousFocusRef.current.focus(); previousFocusRef.current = null }
  }, [contextOpen])

  async function submitQuestion(question: string) {
    const trimmed = question.trim()
    if (!trimmed || inFlightRef.current) return
    const generation = generationRef.current
    const previousMessages = messages
    const nextMessages: ChatItem[] = [...previousMessages, { role: 'user', content: trimmed }]
    inFlightRef.current = true
    setMessages(nextMessages)
    setDraft('')
    setError(null)
    setLoading(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const response = await sendMessage(trimmed, safeHistory, controller.signal)
      if (generation !== generationRef.current) return
      setMessages([...nextMessages, { role: 'assistant', content: response.answer, stopReason: response.stop_reason, events: response.events }])
    } catch (requestError) {
      if (generation !== generationRef.current) return
      setMessages(previousMessages)
      setDraft(trimmed)
      setError(controller.signal.aborted ? 'Request cancelled.' : requestError instanceof Error ? requestError.message : 'Mirai could not answer this question.')
    } finally {
      if (generation === generationRef.current) {
        inFlightRef.current = false
        setLoading(false)
        abortRef.current = null
      }
    }
  }

  function startNewConversation() {
    generationRef.current += 1
    abortRef.current?.abort()
    abortRef.current = null
    inFlightRef.current = false
    setMessages([])
    setDraft('')
    setError(null)
    setLoading(false)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void submitQuestion(draft) }
  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submitQuestion(draft) } }

  const titleId = `${idPrefix}-title`
  const composerId = `${idPrefix}-composer`
  const drawerTitleId = `${idPrefix}-context-title`
  const TitleTag = titleLevel

  return (
    <section className="relative min-h-[calc(100vh-250px)]" aria-labelledby={titleId}>
      <header className="flex flex-col gap-3 border-b border-white/[0.10] pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0"><TitleTag id={titleId} className="text-xl font-semibold text-white">{title}</TitleTag><p className="mt-1 truncate text-sm text-slate-200" title={contextSummary}>{contextSummary}</p><p className="mt-1 text-xs text-[#9FB0C8]">{groundingSummary}</p></div>
        <div className="flex flex-wrap gap-2">{messages.length > 0 && <button type="button" onClick={startNewConversation} className="rounded-md px-3 py-2 text-sm font-semibold text-slate-200 hover:bg-white/[0.05]">New conversation</button>}<button type="button" onClick={() => setContextOpen(true)} aria-expanded={contextOpen} className="rounded-md border border-white/[0.12] px-3 py-2 text-sm font-semibold text-[#BDEAFF] hover:bg-[#74C7F5]/10">Project context</button></div>
      </header>

      <div className="mx-auto flex min-h-[calc(100vh-330px)] w-full max-w-[54rem] flex-col">
        <div className="flex-1 py-8 sm:py-10" aria-label="Conversation">
          {messages.length === 0 ? <ChatEmptyState heading={emptyHeading} description={emptyDescription} suggestions={suggestions} onSuggestion={setDraft} /> : <ConversationView messages={messages} loading={loading} loadingLabel={loadingLabel} bottomRef={bottomRef} />}
        </div>
        <div className="sticky bottom-0 z-10 bg-[linear-gradient(180deg,transparent,#050914_18%)] pb-4 pt-8">
          {error && <div className="mb-3 flex items-center justify-between gap-3 rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-100"><span>{error}</span><button type="button" onClick={() => void submitQuestion(draft)} disabled={!draft.trim() || loading} className="font-semibold underline disabled:opacity-50">Try again</button></div>}
          <ChatComposer id={composerId} label={composerLabel} placeholder={placeholder} draft={draft} loading={loading} onDraftChange={setDraft} onKeyDown={handleComposerKeyDown} onSubmit={handleSubmit} onCancel={() => abortRef.current?.abort()} />
        </div>
      </div>

      <div className="sr-only" aria-live="polite">{loading ? loadingLabel : messages[messages.length - 1]?.role === 'assistant' ? 'Mirai added a response.' : ''}</div>
      {contextOpen && <ProjectContextDrawer titleId={drawerTitleId} closeButtonRef={closeButtonRef} context={context} onClose={() => setContextOpen(false)} />}
    </section>
  )
}

function ChatEmptyState({ heading, description, suggestions, onSuggestion }: { heading: string; description: string; suggestions: string[]; onSuggestion: (question: string) => void }) {
  return <div className="mx-auto max-w-2xl py-10 text-center sm:py-16"><h2 className="text-2xl font-semibold tracking-[-0.035em] text-white">{heading}</h2><p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-[#AAB6C8]">{description}</p><div className="mx-auto mt-8 grid max-w-2xl gap-2 sm:grid-cols-2">{suggestions.slice(0, 4).map((question) => <button key={question} type="button" onClick={() => onSuggestion(question)} className="rounded-md border border-white/[0.10] px-4 py-3 text-left text-sm leading-5 text-slate-200 transition hover:border-[#5BA8FF]/35 hover:bg-[#5BA8FF]/[0.07]">{question}</button>)}</div></div>
}

function ConversationView({ messages, loading, loadingLabel, bottomRef }: { messages: ChatItem[]; loading: boolean; loadingLabel: string; bottomRef: RefObject<HTMLDivElement> }) {
  return <div className="space-y-8">{messages.map((message, index) => <article key={`${message.role}-${index}`} className={message.role === 'user' ? 'flex justify-end' : ''}>{message.role === 'user' ? <UserMessage content={message.content} /> : <AssistantMessage message={message} />}</article>)}{loading && <div className="flex items-center gap-3 text-sm text-[#AAB6C8]"><span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#74C7F5]/25 border-t-[#74C7F5]" />{loadingLabel}</div>}<div ref={bottomRef} /></div>
}

function UserMessage({ content }: { content: string }) { return <div className="max-w-[86%] rounded-xl bg-[#17335E]/70 px-4 py-3 text-sm leading-6 text-white sm:max-w-[75%]"><MessageContent content={content} /></div> }

function AssistantMessage({ message }: { message: ChatItem }) {
  return <div className="max-w-none text-[15px] leading-7 text-[#D7DEEA]"><p className="mb-2 text-xs font-semibold text-[#8FCBFF]">Mirai</p><MessageContent content={message.content} />{!!message.events?.length && <EvidenceReferences events={message.events} />}{message.stopReason && message.stopReason !== 'completed' && <p className="mt-3 text-xs text-amber-100">Response ended: {readableValue(message.stopReason)}</p>}</div>
}

function EvidenceReferences({ events }: { events: DataScientistEvent[] }) {
  return <details className="mt-4 border-t border-white/[0.08] pt-3 text-xs text-[#9FB0C8]"><summary className="cursor-pointer font-semibold text-[#BDEAFF]">Activity trail ({events.length})</summary><div className="mt-3 space-y-2">{events.map((event, index) => <div key={`${event.label}-${index}`}><span className="font-medium text-slate-200">{event.label}</span>{event.tool_name && <span> · {event.tool_name}</span>}{event.detail && <p className="mt-1 leading-5">{event.detail}</p>}</div>)}</div></details>
}

function ChatComposer({ id, label, placeholder, draft, loading, onDraftChange, onKeyDown, onSubmit, onCancel }: { id: string; label: string; placeholder: string; draft: string; loading: boolean; onDraftChange: (value: string) => void; onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onCancel: () => void }) {
  return <form onSubmit={onSubmit} className="rounded-2xl border border-white/[0.14] bg-[#0B1424] p-3 shadow-[0_18px_45px_rgba(0,0,0,0.28)]"><label htmlFor={id} className="sr-only">{label}</label><textarea id={id} value={draft} onChange={(event) => onDraftChange(event.target.value)} onKeyDown={onKeyDown} rows={2} maxLength={4000} placeholder={placeholder} className="max-h-48 min-h-[3.25rem] w-full resize-y border-0 bg-transparent px-1 py-1 text-[15px] leading-6 text-white outline-none placeholder:text-[#74839B]" /><div className="mt-2 flex items-center justify-between gap-3 border-t border-white/[0.08] pt-3"><p className="text-xs text-[#8493AA]">Enter to send · Shift+Enter for a new line</p><div className="flex items-center gap-2">{loading && <button type="button" onClick={onCancel} className="rounded-md px-3 py-2 text-sm font-semibold text-[#BDEAFF] hover:bg-[#74C7F5]/10">Cancel</button>}<button type="submit" disabled={loading || !draft.trim()} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4C7DFF] disabled:cursor-not-allowed disabled:opacity-45">{loading ? 'Thinking…' : 'Send'}</button></div></div></form>
}

function ProjectContextDrawer({ titleId, closeButtonRef, context, onClose }: { titleId: string; closeButtonRef: RefObject<HTMLButtonElement>; context: ChatWorkspaceProps['context']; onClose: () => void }) {
  return <div className="fixed inset-0 z-[110] flex justify-end bg-black/50" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}><aside role="dialog" aria-modal="true" aria-labelledby={titleId} className="h-full w-full max-w-md overflow-y-auto border-l border-white/[0.12] bg-[#08111F] p-5 sm:p-6"><div className="flex items-start justify-between gap-4 border-b border-white/[0.10] pb-4"><div><h2 id={titleId} className="text-lg font-semibold text-white">Project context</h2><p className="mt-1 text-xs text-[#9FB0C8]">{context.scopeSummary}</p></div><button ref={closeButtonRef} type="button" onClick={onClose} aria-label="Close project context" className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/[0.12] text-xl text-white hover:bg-white/[0.06]">×</button></div>{context.description && <p className="mt-5 text-sm leading-6 text-[#B8C2D4]">{context.description}</p>}<dl className="mt-6 grid grid-cols-2 gap-5 text-sm">{context.items.map((item) => <ContextItem key={item.label} {...item} />)}</dl>{context.artifacts !== undefined && <section className="mt-7 border-t border-white/[0.10] pt-5"><h3 className="text-sm font-semibold text-white">Available artifacts</h3>{context.artifacts.length ? <ul className="mt-3 space-y-2 text-sm text-[#B8C2D4]">{context.artifacts.map((artifact) => <li key={`${artifact.label}-${artifact.detail ?? ''}`}><span className="font-medium text-slate-100">{artifact.label}</span>{artifact.detail && <span className="mt-0.5 block truncate text-xs text-[#8493AA]" title={artifact.detail}>{artifact.detail}</span>}</li>)}</ul> : context.emptyArtifactsCopy ? <p className="mt-3 text-sm text-[#9FB0C8]">{context.emptyArtifactsCopy}</p> : null}</section>}{context.actions?.length ? <section className="mt-7 border-t border-white/[0.10] pt-5"><h3 className="text-sm font-semibold text-white">Return to workflow</h3><div className="mt-3 flex flex-wrap gap-2">{context.actions.map((action) => <button key={action.label} type="button" onClick={() => { onClose(); action.onClick() }} className="rounded-md border border-white/[0.10] px-3 py-2 text-sm font-semibold text-[#BDEAFF] hover:bg-[#74C7F5]/10">{action.label}</button>)}</div></section> : null}</aside></div>
}

function ContextItem({ label, value }: ChatContextItem) { return <div className="min-w-0"><dt className="text-xs text-[#9FB0C8]">{label}</dt><dd className="mt-1 break-words font-medium text-white" title={value}>{value}</dd></div> }

export function MessageContent({ content }: { content: string }) {
  return <div className="space-y-3 break-words">{parseChatMarkdown(content).map((block, index) => {
    if (block.type === 'heading') { const Tag = block.level === 1 ? 'h2' : block.level === 2 ? 'h3' : 'h4'; return <Tag key={index} className="pt-2 font-semibold text-white"><InlineText text={block.text} /></Tag> }
    if (block.type === 'unordered-list') return <ul key={index} className="list-disc space-y-1 pl-5">{block.items.map((item, itemIndex) => <li key={itemIndex}><InlineText text={item} /></li>)}</ul>
    if (block.type === 'ordered-list') return <ol key={index} className="list-decimal space-y-1 pl-5">{block.items.map((item, itemIndex) => <li key={itemIndex}><InlineText text={item} /></li>)}</ol>
    if (block.type === 'code') return <pre key={index} className="overflow-x-auto rounded-md bg-black/25 p-3 font-mono text-xs leading-5 text-slate-200"><code>{block.text}</code></pre>
    if (block.type === 'table') return <div key={index} className="overflow-x-auto"><table className="min-w-full divide-y divide-white/[0.10] text-left text-sm"><thead><tr>{block.headers.map((header) => <th key={header} className="px-3 py-2 font-semibold text-white"><InlineText text={header} /></th>)}</tr></thead><tbody className="divide-y divide-white/[0.08]">{block.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex} className="px-3 py-2"><InlineText text={cell} /></td>)}</tr>)}</tbody></table></div>
    return <p key={index}><InlineText text={block.text} /></p>
  })}</div>
}

function InlineText({ text }: { text: string }) {
  return <>{text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index} className="rounded bg-black/25 px-1.5 py-0.5 font-mono text-[0.9em] text-slate-100">{part.slice(1, -1)}</code>
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index} className="font-semibold text-white">{part.slice(2, -2)}</strong>
    return <Fragment key={index}>{part}</Fragment>
  })}</>
}

function readableValue(value: string) { const readable = value.replace(/[_-]+/g, ' ').trim(); return readable ? readable.charAt(0).toUpperCase() + readable.slice(1) : 'Unknown' }
