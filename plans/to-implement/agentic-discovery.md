# TASK: Architecture Discovery & Integration Planning for Agentic Engineering Knowledge Intake

## Context

Mirai currently has a working platform centered around:

```text
Data Intake
→ Agentic Preprocessing
→ Preprocessing Review
→ Training Request
→ Model Training
→ Optimization / Recommendations
→ Diagnostics / Business Impact
```

This workflow already works and must remain intact.

Recent customer conversations in:

- Mining
- Railways
- Industrial Operations

revealed that the most painful problem often occurs before ML.

Engineering knowledge is frequently scattered across:

- PDFs
- Word documents
- Excel files
- CSV exports
- Maintenance records
- Requirements documents
- Inspection reports
- Operational procedures
- Historical engineering reports
- Sensor exports

Customers repeatedly indicated that transforming this fragmented information into a structured and queryable engineering system would be highly valuable.

The long-term vision is:

```text
Engineering Knowledge
→ Structured Engineering Knowledge
→ ML-Ready Data
→ Models
→ Optimization
→ Decision Support
```

However:

**This task is NOT to implement this capability.**

The task is to fully understand the existing Mirai architecture and determine the safest way to introduce this new capability without damaging anything that already works.

---

# CRITICAL CONSTRAINTS

## DO NOT IMPLEMENT YET

This is an investigation and planning task.

No production implementation should occur.

No architectural rewrites should occur.

No database migrations should occur.

No route changes should occur.

No storage changes should occur.

No new services should be introduced.

No new infrastructure should be provisioned.

---

## DO NOT BREAK EXISTING MIRAI

The current platform is the priority.

Do not:

- Replace the existing agentic preprocessing system
- Replace the current data intake workflow
- Replace the current training workflow
- Replace the optimization workflow
- Replace battery/fuel-cell use cases
- Replace the current storage model
- Change Railway deployment assumptions
- Introduce unnecessary complexity

The goal is to extend Mirai.

Not rebuild Mirai.

---

## EXISTING PIPELINES MUST REMAIN VALID

The following flow must continue to work exactly as it does today:

```text
CSV / Tabular Data
→ Intake
→ Agentic Preprocessing
→ User Approval
→ Training Request
→ Model Training
→ Optimization
```

Any future engineering-document capability should eventually feed into this flow.

Not replace it.

---

# PRIMARY OBJECTIVE

Understand exactly how Mirai works today.

Then identify the safest integration point for a future:

```text
Agentic Engineering Knowledge Intake Layer
```

that could process:

- PDFs
- DOCX
- XLSX
- CSV
- Engineering reports
- Requirements
- Maintenance logs
- Operational documents

and convert them into structured engineering knowledge.

---

# PHASE 1 — FULL SYSTEM DISCOVERY

## Backend Architecture Audit

Perform a complete audit of the backend.

Map:

### API Layer

Identify:

- FastAPI routes
- Route groups
- Data intake endpoints
- Session endpoints
- Training endpoints
- Storage endpoints
- Agent endpoints
- Review/approval endpoints

Create a complete flow map.

---

### Data Flow

Map:

```text
Upload
→ Storage
→ Metadata Extraction
→ Agentic Processing
→ User Review
→ Training Request
→ Training Execution
→ Artifact Storage
→ Recommendation Generation
```

Document every step.

---

### Database Layer

Audit:

- PostgreSQL models
- ORM models
- migrations
- workspace tables
- project tables
- dataset tables
- session tables
- preprocessing tables
- training tables
- recommendation tables

Deliver:

```text
Current database schema overview
```

---

### Storage Layer

Audit:

- S3 usage
- Railway object storage
- bucket organization
- workspace isolation
- project isolation
- session storage
- local filesystem usage
- artifact storage
- MLflow storage

Deliver:

```text
Storage architecture map
```

---

# PHASE 2 — AGENTIC LAYER AUDIT

Investigate the current agentic preprocessing system.

Determine:

### Current Responsibilities

What exactly does the agent do today?

Examples:

- metadata extraction
- schema inference
- preprocessing recommendations
- feature analysis
- data quality analysis

Document everything.

---

### Current Inputs

What does the agent consume?

Examples:

- CSV
- dataframe
- metadata
- EDA results

Document precisely.

---

### Current Outputs

What does the agent generate?

Examples:

- preprocessing plans
- recommendations
- reports
- approvals

Document precisely.

---

### User Approval Flow

Determine:

- how approvals work
- where they are stored
- how the frontend interacts with them
- how state transitions occur

Deliver:

```text
Agentic preprocessing lifecycle
```

---

# PHASE 3 — FUTURE DOCUMENT INTAKE ANALYSIS

Once the existing architecture is understood:

Determine how a future:

```text
Agentic Engineering Knowledge Intake Layer
```

could fit into Mirai.

---

# IMPORTANT PRODUCT PRINCIPLE

The goal is NOT:

```text
PDF
→ Chat
```

The goal is NOT:

```text
PDF
→ Vector DB
→ Chat
```

The goal is:

```text
Documents
→ Structured Engineering Knowledge
→ Structured Tables
→ ML-Ready Datasets
→ Existing Mirai Pipeline
```

Everything should ultimately feed the current platform.

---

# ENGINEERING KNOWLEDGE EXTRACTION CONCEPT

Investigate whether a future agent could extract information using a controlled engineering framework.

Potential extraction questions:

```text
What assets are mentioned?

What systems or subsystems are mentioned?

What requirements are described?

What constraints are specified?

What measurements are provided?

What operating limits are provided?

What maintenance actions are described?

What failure events are described?

What operating conditions are described?

What relationships exist between entities?

What information could become structured columns?

What information is ambiguous?
```

This is NOT implementation.

This is exploration.

Determine whether such a framework could fit naturally into Mirai.

---

# STRUCTURED STORAGE PRINCIPLE

Investigate how Mirai could eventually store extracted engineering knowledge.

The source of truth should likely be structured data.

Not vectors.

Potential future concepts:

```text
SourceDocument
DocumentChunk
ExtractionRun
SchemaVersion

EntityType
Entity

RelationshipType
Relationship

StructuredTable
MLDatasetCandidate
```

Do not implement.

Only evaluate.

---

# EMBEDDINGS & VECTOR SEARCH

Evaluate whether embeddings are even necessary in Phase 1.

Questions:

- Could Postgres alone support the first version?
- Would pgvector be sufficient?
- Is a separate vector database justified?
- Should embeddings be deferred entirely?

Provide recommendations.

No implementation.

---

# PHASE 4 — INTEGRATION STRATEGY OPTIONS

After understanding the system:

Produce multiple integration options.

For each option provide:

## Option A

Description

Pros

Cons

Risk Level

Files Likely Affected

Database Impact

Railway Impact

---

## Option B

Description

Pros

Cons

Risk Level

Files Likely Affected

Database Impact

Railway Impact

---

## Option C

Description

Pros

Cons

Risk Level

Files Likely Affected

Database Impact

Railway Impact

---

# RECOMMENDED APPROACH

Select the safest approach.

The recommendation should be:

- incremental
- reversible
- low risk
- compatible with Railway
- compatible with current storage
- compatible with current preprocessing
- compatible with current training flow

---

# FUTURE HIGH-LEVEL PHASES

Only as a conceptual roadmap.

Something similar to:

```text
Phase 1
Architecture Discovery

Phase 2
Read-Only Document Intake Prototype

Phase 3
Engineering Knowledge Extraction

Phase 4
Schema Review & Approval

Phase 5
Structured Table Generation

Phase 6
Feed Existing Mirai Pipeline

Phase 7
Optional Semantic Search / Embeddings

Phase 8
Knowledge-Aware ML Workflows
```

Do not implement these phases.

Only evaluate feasibility.

---

# QUESTIONS THAT MUST BE ANSWERED BEFORE IMPLEMENTATION

The final report must contain a dedicated section:

```text
Questions Requiring Human Decisions
```

Ask every question necessary before coding.

Examples:

- Should document intake be a new dataset type?
- Should engineering knowledge live alongside datasets or separately?
- How should approvals work?
- How should lineage be stored?
- How should schemas be versioned?
- How should cross-industry support be handled?
- What assumptions about Railway are unsafe?
- What assumptions about storage are unsafe?
- What assumptions about the current backend are still unknown?

Be exhaustive.

---

# REQUIRED DELIVERABLE

Produce a single markdown document containing:

1. Current Architecture Map
2. Current Storage Architecture
3. Current Agentic Layer Analysis
4. Current Training Pipeline Analysis
5. Integration Opportunities
6. Integration Risks
7. Multiple Architecture Options
8. Recommended Approach
9. Open Questions
10. Explicit Non-Goals

---

# SUCCESS CRITERIA

Success is NOT code.

Success is a complete understanding of:

- how Mirai works today
- where a future engineering knowledge layer belongs
- how to integrate it without breaking existing workflows

The final recommendation should prioritize preserving the current Mirai platform while identifying the safest path toward:

```text
Engineering Knowledge
→ Structured Data
→ ML
→ Optimization
```

without introducing unnecessary architectural complexity.