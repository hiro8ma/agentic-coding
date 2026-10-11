## AI-DLC v1.0.1

When the user explicitly requests the AI-DLC v1 workflow, read
`.aidlc/aidlc-rules/aws-aidlc-rules/core-workflow.md`.
Load relevant details from `.aidlc/aidlc-rules/aws-aidlc-rule-details/` as directed by that workflow.

Preserve the existing project rules and the user's authorized scope.
Treat missing rules or an unknown upstream version as unverified setup; report the mismatch before using the workflow.
Use the project's existing specification files as the source of truth and record the relationship of any additional artifacts.
This fragment applies to v1.0.1; it does not install the current AI-DLC harness, hooks, or skills.
