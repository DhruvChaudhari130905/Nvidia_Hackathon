---
name: example-clean-code
description: Keep changes small and readable - clear names, short functions, no dead code. Use for any code change.
---

# Clean code

When you change code:

1. Name things for what they mean in the app ("cartTotal", not "x2").
2. Keep functions short; split one that does two jobs.
3. Delete code you replace. No commented-out blocks, no unused imports.
4. Match the file's existing style: quotes, indentation, naming.
5. Handle the failure a user can actually hit (empty list, network error) with a clear message.
