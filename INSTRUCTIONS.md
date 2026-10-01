# Engineering Instructions

These rules apply to the entire repository.

## Engineering style

Write production code as if it were authored and maintained by the engineering team.

- Prefer simple, direct implementations over speculative abstractions.
- Make the smallest coherent change that satisfies the requirement.
- Preserve existing conventions unless there is a concrete reason to change them.
- Use precise domain names. Avoid generic names such as `manager`, `helper`, or `processor` when a domain-specific name exists.
- Comments explain intent, constraints, trade-offs, or non-obvious behavior. Do not narrate obvious code.
- Avoid unnecessary comments, verbose docstrings, placeholder abstractions, gratuitous wrappers, and boilerplate.
- Repository code and committed documentation must not contain meta-commentary about how code was generated or implementation conversations.
- Do not add references to prompts, coding assistants, ChatGPT, Claude, Copilot, or agents unless the product functionality explicitly requires such a reference.
- Do not optimize for appearing clever. Optimize for correctness, readability, maintainability, and testability.

## Change discipline

Before changing behavior:

1. Understand the requirement and acceptance criteria.
2. Read the owning module's README, CODE.md, relevant source, and tests.
3. Identify assumptions and dependencies.
4. Prefer a focused change over unrelated cleanup.
5. Add or update automated tests for behavior that can reasonably be tested.
6. Run the owning module's tests.
7. Run relevant integration/regression tests before completion.

For a bug fix, normally add a regression test that demonstrates the failure before the fix and passes afterward.

A feature is not complete merely because the implementation runs. Its acceptance criteria should be protected by automated tests where practical.

## Modules

A business capability should live in an owning module. A module may contain:

- `README.md` — purpose, boundaries, dependencies, public interfaces.
- `quickstart.md` — minimum commands and steps to run/test/debug.
- `CODE.md` — concise code map for maintainers and coding tools.
- `ui/` — optional module UI.
- `service/` — optional backend/service implementation.
- `tests/` — module tests.

Do not create empty layers simply to satisfy this shape.

The top-level application is a composition shell. It owns concerns such as layout, navigation, authentication/session integration, module registration, global notifications, and application-wide theming. Business logic belongs in modules.

## UI

The application must support light and dark themes. System preference should be supported as the default unless a later product requirement overrides it.

Theme behavior belongs to the application shell. Module UIs consume shared design tokens/components and must work correctly in both themes. Modules must not invent independent theme systems.

## Runtime modes

The platform has two runtime modes:

- `local`: all required application infrastructure runs locally. Development and automated testing must not require Oracle Cloud, Vercel, Supabase, or a live broker.
- `deployed`: components use the configured production/deployed infrastructure.

Business logic should depend on interfaces/configuration rather than branching throughout the code on runtime mode.

## Security

Never commit credentials, tokens, private keys, broker secrets, production environment files, private prompts, or private working notes.

Private local material belongs under ignored paths such as `.pat/`, `.docs/`, and `prompts/`.

Secrets must be supplied through environment/deployment secret mechanisms. Never log secrets.

## Documentation

Documentation is intentionally small and layered. Do not create documentation merely because a change was made.

Keep committed docs current, concise, and close to the code they describe. Detailed brainstorming, temporary research, rejected designs, and private working context belong in `.docs/` and are not committed.
