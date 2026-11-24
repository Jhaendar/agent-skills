# Book Skills

A curated collection of modular agent skills distilled from foundational software engineering books, structured for **Google Antigravity** and compatible `SKILL.md`-based AI coding agents.

Each skill compresses a book's mental models, opinionated rules, schema conventions, and anti-patterns into a lightweight `SKILL.md` router backed by focused `references/*.md` files and deterministic `scripts/` helpers where useful.

## Included Skills

| Skill | Source Book | Scope |
| :--- | :--- | :--- |
| [`api-design-patterns`](./skills/api-design-patterns/SKILL.md) | *API Design Patterns* — JJ Geewax (Manning) | Designing, reviewing, and linting resource-oriented web APIs: greenfield vs. brownfield precedence, HTTP wire bindings, naming & units, resource hierarchy, Base32/Base37 checksum IDs, standard & `:custom` methods, `FieldMask`, LROs, jobs, relationships, batch/collective operations, cursor pagination, filtering, versioning, soft deletion, deduplication, retries, and request signing — plus a zero-dependency CLI tool (`id-gen`, `id-verify`, `lint-openapi`). |

## Repository Structure

```text
book-skills/
├── .gitignore
├── .agents/
│   └── skills.json                      # Enables workspace-local discovery in Antigravity
├── README.md
└── skills/
    └── api-design-patterns/
        ├── SKILL.md                     # Compact router, wire rules, guardrails & output contracts
        ├── scripts/
        │   └── api_patterns_tool.py     # Zero-dependency CLI: id-gen, id-verify, lint-openapi
        └── references/                  # Progressive-disclosure deep-dive references
            ├── 01-design-principles.md
            ├── 02-fundamentals.md
            ├── 03-resource-relationships.md
            ├── 04-collective-operations.md
            └── 05-safety-and-security.md
```

## Architecture & Progressive Disclosure

Antigravity loads only each skill's YAML frontmatter (`name` and `description`) at startup. When a skill activates:

1. The agent reads `SKILL.md` for scope precedence (greenfield vs. brownfield), HTTP wire mappings, core invariants, and deliverable formats.
2. Based on the routing table, it selectively loads only the 1–2 relevant `references/*.md` files, keeping token overhead minimal.
3. For deterministic tasks (generating/verifying Base32+Base37 checksum IDs or linting OpenAPI specs), it runs `scripts/api_patterns_tool.py`.

Where book guidance is supplemented with modern industry standards (e.g., RFC 9110, RFC 9457 Problem Details, RFC 9421 HTTP Message Signatures, OAuth 2.0 / OIDC, optimistic concurrency `ETag`/`If-Match`, `orderBy`), those additions are explicitly marked as industry supplements.

## How to Install in Antigravity

### Option 1: Global (Available Across All Workspaces)

Add this repository's `skills` directory to `~/.gemini/config/skills.json`:

```json
{
  "entries": [
    {
      "path": "/Users/jhaendar/Obsidian/TEST /book-skills/skills"
    }
  ]
}
```

> **Note:** If you move this repository (for example, to `~/Projects/book-skills`), update the `path` value in `~/.gemini/config/skills.json` accordingly.

### Option 2: Project-Local

In any repository, create `.agents/skills.json` pointing to this repo's `skills` folder:

```json
{
  "entries": [
    {
      "path": "/Users/jhaendar/Obsidian/TEST /book-skills/skills"
    }
  ]
}
```

Alternatively, add this repo as a git submodule or copy an individual `skills/<skill-name>` folder directly into `.agents/skills/`.

## Adding Future Book Skills

1. Create a new directory under `skills/<kebab-case-skill-name>/`.
2. Add `SKILL.md` with lowercase hyphenated `name` and third-person `description` frontmatter (including explicit `Trigger for` and `DO NOT trigger for` boundaries), keeping the main file concise (~100–200 lines).
3. Split deep chapter/topic references into `references/` and link them via relative Markdown paths from `SKILL.md`.
4. Add deterministic `scripts/` helpers whenever the book defines algorithms or lintable spec rules.
5. Separate book-canonical conventions from any >90%-confidence industry supplements.
6. Update the **Included Skills** table above.
