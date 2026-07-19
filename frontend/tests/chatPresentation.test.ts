import assert from 'node:assert/strict'
import test from 'node:test'
import type { ProjectSchema } from '../src/lib/api.ts'
import { dataScientistSuggestions, humanizeChatValue, parseChatMarkdown } from '../src/lib/chatPresentation.ts'

const schema: ProjectSchema = {
  project_id: 'project-1',
  display_name: 'Cathode degradation',
  inputs: [
    { name: 'temperature', label: 'Temperature', type: 'continuous', min: 20, max: 90, unit: '°C' },
    { name: 'humidity', label: 'Humidity', type: 'continuous', min: 0, max: 100, unit: '%' },
  ],
  outputs: [{ name: 'degradation', label: 'Degradation', direction: 'minimize', unit: '%' }],
}

test('Data Scientist suggestions are project-specific and limited to four', () => {
  const suggestions = dataScientistSuggestions(schema)
  assert.equal(suggestions.length, 4)
  assert.match(suggestions[1], /3 modeled variables/)
  assert.ok(suggestions.some((question) => question.includes('preprocessing')))
  assert.ok(suggestions.some((question) => question.includes('model-quality')))
})

test('project context values are humanized safely', () => {
  assert.equal(humanizeChatValue('generic_tabular_doe'), 'Generic tabular DoE')
  assert.equal(humanizeChatValue(''), 'Not available')
})

test('chat Markdown groups semantic headings and lists', () => {
  const blocks = parseChatMarkdown('# Summary\n\n- First\n- Second\n\n1. Review\n2. Approve')
  assert.deepEqual(blocks[0], { type: 'heading', level: 1, text: 'Summary' })
  assert.deepEqual(blocks[1], { type: 'unordered-list', items: ['First', 'Second'] })
  assert.deepEqual(blocks[2], { type: 'ordered-list', items: ['Review', 'Approve'] })
})

test('chat Markdown keeps fenced code in one block', () => {
  const blocks = parseChatMarkdown('```python\nprint("mirai")\nvalue = 2\n```')
  assert.deepEqual(blocks, [{ type: 'code', language: 'python', text: 'print("mirai")\nvalue = 2' }])
})

test('chat Markdown renders tables as structured data', () => {
  const blocks = parseChatMarkdown('| Variable | Role |\n| --- | --- |\n| RH | input |')
  assert.deepEqual(blocks, [{ type: 'table', headers: ['Variable', 'Role'], rows: [['RH', 'input']] }])
})
