import type { ProjectSchema } from './api'

export type ChatMarkdownBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'heading'; level: 1 | 2 | 3; text: string }
  | { type: 'unordered-list'; items: string[] }
  | { type: 'ordered-list'; items: string[] }
  | { type: 'code'; language: string; text: string }
  | { type: 'table'; headers: string[]; rows: string[][] }

export function dataScientistSuggestions(schema: ProjectSchema): string[] {
  const suggestions = [
    'What uploaded data is available for this project?',
    `Summarize this dataset and its ${schema.inputs.length + schema.outputs.length} modeled variables.`,
    'Explain the preprocessing decisions and any data-quality concerns.',
    'Summarize the available model-quality and training results.',
  ]
  return suggestions.slice(0, 4)
}

export function humanizeChatValue(value?: string | null): string {
  if (value === 'generic_tabular_doe') return 'Generic tabular DoE'
  const readable = String(value ?? '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return readable ? readable.charAt(0).toUpperCase() + readable.slice(1) : 'Not available'
}

export function parseChatMarkdown(content: string): ChatMarkdownBlock[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: ChatMarkdownBlock[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) { index += 1; continue }

    const fence = line.trim().match(/^```([^\s]*)/)
    if (fence) {
      const code: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) { code.push(lines[index]); index += 1 }
      if (index < lines.length) index += 1
      blocks.push({ type: 'code', language: fence[1], text: code.join('\n') })
      continue
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length as 1 | 2 | 3, text: heading[2] })
      index += 1
      continue
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) { items.push(lines[index].replace(/^[-*]\s+/, '')); index += 1 }
      blocks.push({ type: 'unordered-list', items })
      continue
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) { items.push(lines[index].replace(/^\d+\.\s+/, '')); index += 1 }
      blocks.push({ type: 'ordered-list', items })
      continue
    }

    if (line.includes('|') && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])) {
      const headers = tableCells(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) { rows.push(tableCells(lines[index])); index += 1 }
      blocks.push({ type: 'table', headers, rows })
      continue
    }

    const paragraph: string[] = [line.trim()]
    index += 1
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines, index)) { paragraph.push(lines[index].trim()); index += 1 }
    blocks.push({ type: 'paragraph', text: paragraph.join(' ') })
  }

  return blocks
}

function tableCells(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}

function isBlockStart(lines: string[], index: number): boolean {
  const line = lines[index]
  return /^```/.test(line.trim()) || /^#{1,3}\s+/.test(line) || /^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line) || (line.includes('|') && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1]))
}
