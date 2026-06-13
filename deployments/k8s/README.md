# Kubernetes / Level 3 Placeholder

This folder is reserved for future Level 3 deployment work.

Expected future direction:

- Managed Kubernetes, not nested Kind inside Railway.
- Namespace or cluster isolation per client/workspace.
- Per-tenant service accounts/IAM policies for buckets.
- NetworkPolicies, External Secrets, and production ingress/SSO controls.
- Optional namespace-scoped MLflow UI and admin/debug services.

For Level 2, keep Kubernetes manifests out of the active runtime and use Railway-native services.
