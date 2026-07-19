import type { IngestionSessionResponse } from '../../lib/api'
import { askDataScientist } from '../../lib/api'
import { artifactDisplayName, preparationStatusLabel, type PreparationFacts, type PreparationTab, suggestedPreparationQuestions } from '../../lib/preparationPresentation'
import { ChatWorkspace } from '../chat/ChatWorkspace'

export function AskMiraiWorkspace({ projectId, projectName, session, facts, usableRows, inputCount, outputCount, artifacts, variableLabels, contextualPrompt, onNavigate }: {
  projectId: string
  projectName: string
  session: IngestionSessionResponse | null
  facts: PreparationFacts
  usableRows: number | null
  inputCount: number
  outputCount: number
  artifacts: string[]
  variableLabels: string[]
  contextualPrompt: string
  onNavigate: (tab: PreparationTab) => void
}) {
  const sessionId = session?.ingestion_session_id ?? 'none'
  return (
    <ChatWorkspace
      idPrefix="preparation-ask-mirai"
      scopeKey={`${projectId}:${sessionId}`}
      title="Ask Mirai"
      titleLevel="h2"
      contextSummary={`${projectName}${session ? ` · ${session.dataset_id}` : ''}`}
      groundingSummary="Grounded in preparation artifacts"
      emptyHeading="Ask about your preprocessing plan"
      emptyDescription="Mirai answers using this project’s metadata, dataset analysis, preprocessing state, and generated artifacts available through its read-only tools."
      suggestions={suggestedPreparationQuestions(facts, variableLabels)}
      composerLabel="Ask about this project"
      placeholder="Ask about this project…"
      contextualPrompt={contextualPrompt}
      context={{
        scopeSummary: 'Project-scoped · Read only',
        description: 'Mirai can inspect scoped preparation evidence and explain it, but cannot approve or run workflow actions from the conversation.',
        items: [
          { label: 'Project', value: projectName },
          { label: 'Dataset', value: session?.dataset_id ?? 'No session selected' },
          { label: 'Usable rows', value: usableRows === null ? 'Pending' : usableRows.toLocaleString() },
          { label: 'Variables', value: `${inputCount} inputs · ${outputCount} outputs` },
          { label: 'Preparation', value: preparationStatusLabel(facts.mlPreprocessingReady ? 'ml_preprocessing_ready_for_training' : facts.preprocessingStatus) },
          { label: 'Training', value: preparationStatusLabel(facts.trainingStatus) },
        ],
        artifacts: artifacts.map((artifact) => ({ label: artifactDisplayName(artifact), detail: artifact })),
        emptyArtifactsCopy: 'No generated preparation artifacts are available yet.',
        actions: (['variables', 'preprocessing', 'training'] as PreparationTab[]).map((tab) => ({ label: preparationStatusLabel(tab), onClick: () => onNavigate(tab) })),
      }}
      sendMessage={(message, history, signal) => {
        const prefix = session ? `For the selected preparation session ${session.ingestion_session_id}, ` : ''
        return askDataScientist(projectId, `${prefix}answer this project-preparation question using scoped read-only tools as needed: ${message}`, history, signal)
      }}
    />
  )
}
