import type { ProjectSchema } from '../lib/api'
import { askDataScientist } from '../lib/api'
import { dataScientistSuggestions, humanizeChatValue } from '../lib/chatPresentation'
import { ChatWorkspace } from './chat/ChatWorkspace'

export function DataScientistPage({ schema }: { schema: ProjectSchema }) {
  const workspace = schema.workspace_name ?? schema.workspace_id ?? 'Current workspace'
  const template = schema.domain_metadata?.label ?? schema.metadata?.template_id ?? schema.domain_metadata?.template_id

  return (
    <ChatWorkspace
      idPrefix="data-scientist"
      scopeKey={schema.project_id}
      title="Data Scientist"
      contextSummary={schema.display_name}
      groundingSummary="Grounded in this project’s data and model artifacts"
      emptyHeading="Ask about your project data"
      emptyDescription="Explore the uploaded dataset, preprocessing decisions, model quality, and training results."
      suggestions={dataScientistSuggestions(schema)}
      composerLabel="Ask about your project data"
      placeholder="Ask about your project data…"
      context={{
        scopeSummary: 'Project-scoped · Read only',
        description: 'Mirai can query safe project data, preprocessing summaries, model-quality evidence, and active training artifacts through scoped read-only tools.',
        items: [
          { label: 'Workspace', value: workspace },
          { label: 'Project', value: schema.display_name },
          { label: 'Inputs', value: schema.inputs.length.toLocaleString() },
          { label: 'Outputs', value: schema.outputs.length.toLocaleString() },
          { label: 'Modeled variables', value: (schema.inputs.length + schema.outputs.length).toLocaleString() },
          { label: 'Project type', value: template ? humanizeChatValue(String(template)) : 'Generic engineering project' },
        ],
      }}
      sendMessage={(message, history, signal) => askDataScientist(schema.project_id, message, history, signal)}
    />
  )
}
