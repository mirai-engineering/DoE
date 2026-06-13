# Local Kind Deployment Placeholder

This folder is reserved for a future local, prod-like Kubernetes development stack.

Intent:

- Mirror the durable-state architecture used on Railway.
- Provide local access to MLflow UI, MinIO console, Postgres, and app services through port-forwarding or mapped ports.
- Borrow CAI's useful Kubernetes/Helm patterns without making Kind part of the Railway runtime.

Non-goal for now:

- This is not the active Level 2 deployment path.
- Do not add runnable manifests until the Railway stateful path is working and there is a concrete need for local Kubernetes parity.
