# Repository Navigation

Use this file as the entry point when making code changes.

## Context loading order

For work scoped to a module:

1. Read `INSTRUCTIONS.md`.
2. Read this file.
3. Read the module's `README.md`.
4. Read the module's `CODE.md`.
5. Read the module's relevant tests.
6. Inspect only source files needed for the task.
7. Follow dependencies into another module only when the task requires it.

Do not load or summarize the whole repository by default.

## Working method

- Translate the request into concrete acceptance criteria.
- State uncertain assumptions before building around them.
- Locate the owning module and preserve its boundary.
- Prefer surgical changes.
- Reuse established patterns before introducing new ones.
- Add/update tests with behavioral changes.
- Run focused tests first, then relevant regression/integration tests.
- Do not silently change unrelated behavior.
- Keep CODE.md accurate when entry points, invariants, or important flows materially change.

## Context locality goal

A normal module change should be possible by reading this file, `INSTRUCTIONS.md`, the module's README/CODE.md, its tests, and the relevant source files. If routine changes repeatedly require repository-wide exploration, improve the module boundary or its concise code map rather than adding broad documentation.

## Private paths

Do not depend on or commit content from:

- `.docs/`
- `prompts/`
- `.pat/`

They may contain local working context or sensitive information.

## External engineering guidance

Apply the project's selected Karpathy-style engineering principles: clarify assumptions, keep solutions simple, make minimal changes, and convert requirements/bugs into verifiable tests. Project-specific rules in `INSTRUCTIONS.md` take precedence.
