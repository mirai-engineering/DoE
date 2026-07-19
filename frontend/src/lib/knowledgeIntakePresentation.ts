const STATUS_LABELS: Record<string, string> = {
  approved_persistent: 'Approved',
  needs_user_input: 'Needs your input',
  validation_ready: 'Ready for validation',
  validation_passed: 'Validation passed',
  validated: 'Validated',
  exported: 'Exported',
  uploaded: 'Uploaded',
  parsed: 'Indexed',
  completed: 'Complete',
  complete: 'Complete',
  processing: 'Processing',
  running: 'In progress',
  pending: 'Pending',
  failed: 'Failed',
  error: 'Error',
  missing: 'Missing',
  mapped: 'Mapped',
}

export function knowledgeIntakeStatusLabel(value?: string | null): string {
  const normalized = String(value ?? '').trim()
  if (!normalized) return 'Not started'
  const known = STATUS_LABELS[normalized.toLowerCase()]
  if (known) return known
  const readable = normalized.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return readable ? readable.charAt(0).toUpperCase() + readable.slice(1) : 'Not started'
}

export function knowledgeIntakeContractLabel(contractId?: string | null): string {
  if (!contractId) return 'Contract not selected'
  if (contractId === 'generic_tabular_doe') return 'Generic tabular DoE'
  return knowledgeIntakeStatusLabel(contractId)
}
