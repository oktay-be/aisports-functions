---
applyTo: "**"
---
# Project general coding standards

## Principles
- **ALWAYS follow existing patterns**: Before making ANY decision, proposition, or response, check if similar functionality already exists in the project. Verify that your answer aligns with what is already implemented and working. If a pattern exists (e.g., how `batch_builder_function` handles Vertex AI requests), follow it exactly rather than suggesting alternatives.
- Before implementing a functionality (eg. class or function), first check my codebase to see if it or something similar already exists. If it does, reuse it. If something similar exists but is not quite what I need, reuse it and adapt it to my needs.
- **Cross-reference before suggesting changes**: When questioning existing code, search for similar implementations in other functions first (e.g., if reviewing `result_merger_function`, check `batch_builder_function` for the established pattern).
- If you are not sure about the best way to implement something, ask me for guidance.
- When creating files, think where you must create it in my folder hierarchy. If you are not sure, ask me.
- When you remove code piece, even one line, make sure everything you remove really makes sense to remove. Sometimes when inflicting an improvement change, you remove important code pieces too like: "return_exceptions=True"
- When you remove code piece, even one line, make sure to remove all related code pieces (eg. tests, documentation, etc.) that are not needed anymore.
- When I say "create a new file based on another file", make sure in the new file you are not missing any features that the original file has. If you are not sure, ask me.
- When I ask something like "give me", do not edit code. When I say such phrases, just behave as if in ask mode.
- Do not attempt to edit any file unless I told you so.