import assert from 'node:assert/strict'
import test from 'node:test'
import {
  BUSINESS_IMPACT_SCENARIO_DEFAULTS,
  BUSINESS_IMPACT_SECTIONS,
  asImpactRange,
  businessImpactInputError,
  calculateBusinessImpactSavings,
  hoursLabel,
  moneyCompact,
  orderExperimentJourney,
} from '../src/lib/businessImpactPresentation.ts'

test('customer planning scenario retains every default and output', () => {
  assert.deepEqual(BUSINESS_IMPACT_SCENARIO_DEFAULTS, {
    hoursPerCampaign: '520',
    hourlyCost: '150',
    campaignsPerYear: '4',
    reductionPercent: '35',
  })

  const result = calculateBusinessImpactSavings(BUSINESS_IMPACT_SCENARIO_DEFAULTS)
  assert.deepEqual(result, {
    savedHoursPerCampaign: 182,
    savedCostPerCampaign: 27300,
    annualizedSavings: 109200,
  })
  assert.equal(moneyCompact(result.savedCostPerCampaign), '$27k')
  assert.equal(moneyCompact(result.annualizedSavings), '$109k')
})

test('changing each scenario assumption preserves the existing calculation formula', () => {
  assert.deepEqual(calculateBusinessImpactSavings({ ...BUSINESS_IMPACT_SCENARIO_DEFAULTS, hoursPerCampaign: '600' }), {
    savedHoursPerCampaign: 210,
    savedCostPerCampaign: 31500,
    annualizedSavings: 126000,
  })
  assert.deepEqual(calculateBusinessImpactSavings({ ...BUSINESS_IMPACT_SCENARIO_DEFAULTS, hourlyCost: '200' }), {
    savedHoursPerCampaign: 182,
    savedCostPerCampaign: 36400,
    annualizedSavings: 145600,
  })
  assert.deepEqual(calculateBusinessImpactSavings({ ...BUSINESS_IMPACT_SCENARIO_DEFAULTS, campaignsPerYear: '6' }), {
    savedHoursPerCampaign: 182,
    savedCostPerCampaign: 27300,
    annualizedSavings: 163800,
  })
  assert.deepEqual(calculateBusinessImpactSavings({ ...BUSINESS_IMPACT_SCENARIO_DEFAULTS, reductionPercent: '25' }), {
    savedHoursPerCampaign: 130,
    savedCostPerCampaign: 19500,
    annualizedSavings: 78000,
  })
})

test('scenario inputs retain the existing clamp behavior and expose validation messages', () => {
  const result = calculateBusinessImpactSavings({
    hoursPerCampaign: '-50',
    hourlyCost: '150',
    campaignsPerYear: '4',
    reductionPercent: '120',
  })
  assert.deepEqual(result, { savedHoursPerCampaign: 0, savedCostPerCampaign: 0, annualizedSavings: 0 })
  assert.equal(businessImpactInputError('hoursPerCampaign', '-50'), 'Value must be zero or greater.')
  assert.equal(businessImpactInputError('reductionPercent', '120'), 'Reduction must be between 0 and 100%.')
  assert.equal(businessImpactInputError('hourlyCost', ''), 'Enter a numeric value.')
  assert.equal(businessImpactInputError('campaignsPerYear', '4'), null)
})

test('headline, schedule, and operating ranges retain their exact presentation', () => {
  assert.equal(moneyCompact(228000), '$228k')
  assert.equal(moneyCompact(379000), '$379k')
  assert.equal(moneyCompact(21000), '$21k')
  assert.equal(moneyCompact(42000), '$42k')
  assert.equal(hoursLabel(5460), '227.5 days')
  assert.equal(hoursLabel(3640), '151.7 days')
  assert.equal(hoursLabel(1820), '75.8333 days')
  assert.deepEqual(asImpactRange({ low: 228000, high: 379000 }), { low: 228000, high: 379000 })
})

test('experiment journey and evidence fixtures retain every current metric', () => {
  const journey = orderExperimentJourney([
    { label: 'Virtual recipes screened', value: 2000, tone: 'software' },
    { label: 'Historical physical cells learned from', value: 42, tone: 'learned' },
    { label: 'Mirai-prioritized lab recipes', value: 28, tone: 'run' },
    { label: 'Physical recipes avoided', value: 14, tone: 'saved' },
  ])
  assert.deepEqual(journey.map((row) => [row.label, row.value]), [
    ['Historical physical cells learned from', 42],
    ['Virtual recipes screened', 2000],
    ['Mirai-prioritized lab recipes', 28],
    ['Physical recipes avoided', 14],
  ])

  assert.deepEqual(
    {
      physicalCellsInPaper: 49,
      physicalCellsInRepo: 42,
      measuredCurves: 294,
      referencePoints: 6700,
      hoursPerSample: 130,
      virtualCandidates: 2000,
      avoidedPhysicalRecipes: 14,
      savedHandsOnHours: 84,
    },
    {
      physicalCellsInPaper: 49,
      physicalCellsInRepo: 42,
      measuredCurves: 294,
      referencePoints: 6700,
      hoursPerSample: 130,
      virtualCandidates: 2000,
      avoidedPhysicalRecipes: 14,
      savedHandsOnHours: 84,
    },
  )
  assert.deepEqual(BUSINESS_IMPACT_SECTIONS.map((section) => section.label), [
    'Impact story',
    'ROI assumptions',
    'Evidence',
    'References',
  ])
})
