# Before implementing railway

I'd like to not break anything while optimizing `Pi` usage, efficient token management, efficient skills management, etc.

So I'd like to create an mcp client for this repo with the python sdk `https://github.com/modelcontextprotocol/python-sdk`. This client should connect to GitHub's MCP `https://github.com/github/github-mcp-server` so that my coding agent `Pi` can create PR's, branches etc without destroying what I've done so far.

Also, evaluate if we should add `https://pi.dev/packages/context-mode` for this.

Also, `Pi` should ONLY load this MCP to context when needed, not all the time. How?

# Railway Demo Implementation + Data Security Layer

I've added these skills to `Pi`: `https://github.com/addyosmani/agent-skills/tree/main`. There are more intelligent people than me that have the best practices already. The agent should first read these skills and tell me which ones to use for the upcoming plan.

Once this is done and setup, I can reliably proceed with the `railway` deployment strategy. `https://railway.com/`. This strategy could collide with the data privacy and NDA ensurance we, as a startup, provide to our clients.

The Railway demo implementation could collide with the `Data Security Context`, since we talk about usin different namespaces in k8s + GitOps (security level 3), but railway requires a single-container implementation. Your task is to come up with the fastes and efficient solution to this problem. In the following sub-headings I explain the requirements from a client/user-side perspective (an OEM) and in the @sql-s3-implementation/ folder I have the DoE-related requirements, references and context for the actual implementation regarding SQL and S3.

## Data Security Context

Big OEMs using the DoE need to have 100% assurance of no data-leakage of their testing data. So I want to add a security layer. These are 3 layers, and I'd like to implement layer 3:

### Additional Software auth layer before the security layers

The idea is to add Clerk one more time for usage verification and management `https://clerk.com/` so that companies can see "ok, this is serious software that respects data privacy".

The deployed demo should live somewhere like `www.railway.com/mirai-user.mirai-demo` where users can test the live demo with a specific password.

Here is Clerk's installation prompt @clerk-installation-prompt.md

Adding this auth layer should be done in the `clerk-auth` branch, tested to make sure it was successfully added to the frontend, then merge to `main` branch and `railway`

### 3 Security layers

This is a comprehensive architect’s guide to **Multi-Tenant Isolation**. When dealing with high-stakes industries like Automotive, Aerospace, or Defense, this technical depth is what separates a "startup project" from an "**Enterprise-Ready Platform**."

---

#### The Multi-Tenant Security Manifesto: Three Levels of Isolation

In multi-tenancy, your goal is to prevent **Data Cross-Talk**: the situation where Client A accidentally (due to a bug) or maliciously (via an exploit) accesses Client B's intellectual property. We solve this by moving from "Code-based Trust" to "Architecture-based Certainty."

---

##### Level 1: Logical Isolation

*The "Software-Defined" Approach*

**Concept:** You have one single, massive shared infrastructure. You attempt to keep clients apart using your application logic (your Python/TypeScript code).

The Structure:

- **Relational Data (SQL):** A single database containing a single set of tables. Every table includes a mandatory `tenant_id` or `company_id` column.
    - *Data looks like:* `[ID, user_name, company_id]` $\rightarrow$ `[101, 'John', 'OEM_A']`.
- **Object Storage (S3/MinIO):** A single bucket where files are organized by folder prefixes.
    - *Path looks like:* `s3://global-platform-bucket/OEM_A/training_data.csv`.

How to Apply:

You must implement a "Mandatory Filter" in your backend. Every single database query and every single S3 path construction must explicitly inject the `company_id` from the user's secure session.

The Critical Risk: **The Forgotten Clause**

This is the most dangerous level because it relies on human discipline. If a developer writes:
`SELECT * FROM sensitive_data;`
...instead of
`SELECT * FROM sensitive_data WHERE company_id = 'OEM_A';`**The entire database is leaked.** One single forgotten line of code creates a catastrophic security breach.

---

##### Level 2: Virtual Isolation

*The "Database-Engine" Approach*

**Concept:** We stop trusting the application code and start forcing the **Data Engine itself** to enforce security rules. This provides a safety net for human error.

The Structure:

- **Relational Data (SQL):** Using **Row-Level Security (RLS)**. The database engine acts as its own gatekeeper.
    - Instead of filtering in Python, you define a "Policy" inside PostgreSQL that says: *"A user can only see rows if the `company_id` in the row matches the current session variable."*
- **Object Storage (S3/MinIO):** Using **Identity-based Access + Presigned URLs**.
    - The application never gives a user a direct link to a file. Instead, it generates a temporary "Presigned URL" that is valid for only a few minutes and points uniquely to Client A's specific path.

How to Apply:

1. **SQL:** When your backend opens a connection, it runs `SET app.current_tenant = 'OEM_A';`. Every subsequent query is automatically filtered by the database engine. Even if you run `SELECT *`, the DB only returns Client A's rows.
2. **Object Storage:** You implement strict IAM roles or prefix-based policies that restrict access to specific paths based on the authenticated user identity.

The Critical Risk: **The Policy Vulnerability**

While much safer, you are still sharing the same "Engine" (the database process). If there is a vulnerability in the database engine itself, or if your RLS policy is slightly misconfigured (e.g., `OR 1=1`), Client A can still breach Client B.

---

##### Level 3: Physical Isolation

*The "Zero-Trust" Approach*

**Concept:** We move from "Sharing a room" to "Everyone has their own private house." There is no shared database process, no shared memory space, and no shared credentials. This is the gold standard for high-security OEMs.

The Structure:

- **The Infrastructure Unit:** Each client gets their own **Kubernetes Namespace**.
- **Relational Data (SQL):** Instead of one big PostgreSQL instance, Client A has `Postgres_Instance_A`, and Client B has `Posts_Instance_B`. They are physically different processes on the server.
- **Object Storage (S3/MinIO):** Each client gets their own dedicated MinIO bucket or even a separate MinIO service instance.

How to Apply:

1. **Orchestration:** Use a **GitOps** workflow (e.g., ArgoCD). When a new client signs up, your system commits a configuration file to Git.
2. **Deployment:** The GitOps engine sees the change and deplos a fresh "Stack" into a brand-new Namespace for that client.
3. **Network Isolation:** We apply **Kubernetes NetworkPolicies**. This creates a "Digital Wall" around each namespace, ensuring that even if Client A's database is hacked, it is physically impossible for the attacker to even *see* Client B's network address.

The Critical Risk: **The Orchestration Surface**

At this level, the only remaining risk is the "Manager." If an attacker compromises your Kubernetes Control Plane or your GitOps orchestration engine, they can see all clients. However, for 99% of enterprise security audits, Level 3 is considered the ultimate target.

---
Summary Comparison Matrix

| Feature | Level 1: Logical | Level 2: Virtual | Level 3: Physical |
| --- | --- | --- | --- |
| **Core Security Mechanism** | Application Code (`WHERE` clauses) | Database Engine (RLS Policies) | Infrastructure Segregation (Namespaces) |
| **Isolation Type** | Shared Process / Shared DB | Shared Process / Policy-guarded | Separate Process / Separate DB |
| **Complexity** | Very Low | Medium | High |
| **Security Guarantee** | "Trust the Developer" | "Trust the Database" | "Trust the Architecture" |
| **Ideal Use Case** | Early-stage prototyping | General SaaS (B2C/Low-sensitivity B2B) | **Big OEMs / Defense / Aerospace** |


## Railway Roadmap

This is actually a very solid plan already — we're thinking at a **real production architecture level**, but trying to run it on a **fast demo platform**. The key improvement is: we need to slightly *simplify the mental model of Railway* so the agent doesn’t over-AWS it. That's why we're working on the `railway` branch, to simplify the container architecture WITHOUT breaking or destroying the multi-container architecture we have on the `main` branch.

I’ll break this into 3 layers:

---

### **🧠 1. Correct mental model of Railway (important fix)**

Right now your plan still treats Railway like ECS/Lambda:

“single container demo wrapper”

“nginx + backend + proxy orchestration”

That’s **too heavy for Railway**.

#### **Railway reality:**

Railway is just:

```
ONE container = ONE service = ONE exposed port
```

So:

- ❌ No multi-process Nginx + FastAPI orchestration (not needed)
- ❌ No internal service mesh
- ❌ No “production compose translation”
- ❌ No Lambda-style thinking

Instead:

```
Railway runs: 1 Docker container → exposes PORT → done
```

---

### **⚠️ 2. The biggest issue in your plan**

You are currently building:

“single-container demo with nginx + backend + frontend inside”

This is **possible**, but it is:

- fragile
- unnecessary for a demo
- harder to debug on Railway
- not aligned with how Railway is used in practice

---

### **🚀 3. Simplified architecture (what you SHOULD aim for)**

#### **✅ Recommended PATH A (clean Railway version)**

Split reality into:

```
Frontend (React)
Backend (FastAPI)
```

BUT for demo:

**👉 You merge ONLY at build time, not runtime**

---

#### **🟢 Option A1 (BEST): Backend serves frontend**

This is the cleanest Railway setup:

```
Railway container
   ├── FastAPI (port $PORT)
   ├── serves /api/*
   └── serves static frontend build (/)
```

**So:**

- NO Nginx
- NO multi-process
- NO proxy config complexity

FastAPI becomes your “unified server”

---

##### **Architecture becomes:**

```
Browser
  ↓
Railway URL
  ↓
FastAPI
   ├── /api/*
   └── / (React build static files)
```

---

**🔴 What to REMOVE from your plan (important)**

Remove these from PATH A:

- ❌ Nginx container
- ❌ nginx-proxy
- ❌ “two-process entrypoint”
- ❌ docker-compose translation
- ❌ port juggling between nginx/backend
- ❌ local 127.0.0.1 orchestration

These are **ECS/Kubernetes concerns**, not Railway concerns.

---

### **🧩 4. What your Dockerfile.demo SHOULD become**

Instead of your current “mini-production cluster”, simplify:

#### **Single process container:**

##### **Build stage:**

- build React
- copy into FastAPI static folder

##### **Runtime:**

- FastAPI only

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

FastAPI handles:

- `/api/*`
- `/`
- static assets

---

### **🧠 5. Your Tasks — what to adjust**

I’ll refine your plan instead of rewriting everything.

---

#### **🔧 TASK 1 (critical correction)**

**Replace:**

“Nginx + FastAPI + proxy + multi-process”

**With:**

✔ Build React → copy to backend

✔ FastAPI serves everything

✔ Single process runtime

---

#### **🔧 TASK 2 (simplify)**

You don’t need dual healthchecks.

Just:

```
GET /health → FastAPI
```

Railway hits ONE endpoint on ONE port.

---

#### **🔧 TASK 3 (Railway config)**

Your `railway.toml` is fine, but minimal version:

```toml
[build]
dockerfilePath = "Dockerfile.demo"

[deploy]
healthcheckPath = "/health"
```

No restart policy needed for demo.

---

#### **🔧 TASK 4 (important hidden insight)**

Your biggest risk is NOT infra — it’s:

**❗ gitignored ML artifacts**

You correctly identified:

- mlruns
- data-minio
- reference data

**BUT for demo:**

👉 You should NOT ship full ML lifecycle state

Instead:

```
/seed-data
   ├── 3–5 example OEM inputs
   ├── 1 pre-trained model snapshot
   └── static inference outputs
```

Everything else:

- lazy generate
- or externalize later

Otherwise your build becomes fragile + heavy.