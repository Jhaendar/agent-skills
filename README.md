# Book Skills

A curated collection of modular agent skills distilled from foundational software engineering books, structured for **Google Antigravity** and compatible `SKILL.md`-based AI coding agents.

Each skill compresses a book's mental models, opinionated rules, schema conventions, and anti-patterns into a lightweight `SKILL.md` router backed by focused `references/*.md` files.

## Included Skills

| Skill | Source Book | Scope |
| :--- | :--- | :--- |
| [`api-design-patterns`](./skills/api-design-patterns/SKILL.md) | *API Design Patterns* — JJ Geewax (Manning) | Designing, reviewing, and auditing resource-oriented web APIs: naming, resource hierarchy, data types, Base32/checksum IDs, standard & custom methods, field masks, LROs, jobs, relationships, batch/collective operations, pagination, filtering, versioning, soft deletion, deduplication, retries, and request signing. |

## Repository Structure

```text
book-skills/
├── .gitignore
├── .agents/
│   └── skills.json                 # Enables workspace-local discovery in Antigravity
├── README.md
└── skills/
    └── api-design-patterns/
        ├── SKILL.md                # Compact router, workflow checklists, and core rules
        └── references/             # Progressive-disclosure deep-dive references
            ├── 01-design-principles.md
            ├── 02-fundamentals.md
            ├── 03-resource-relationships.md
            ├── 04-collective-operations.md
            └── 05-safety-and-security.md
```

## Architecture & Progressive Disclosure

Antigravity loads only each skill's YAML frontmatter (`name` and `description`) at startup. When a skill activates:

1. The agent reads `SKILL.md` for the core philosophy, step-by-step design/review checklists, and high-signal rules.
2. Based on the pattern routing table, it selectively loads only the relevant `references/*.md` file(s), keeping token overhead minimal.

Where book guidance is supplemented with modern industry standards (e.g., RFC 9110, RFC 9457 Problem Details, RFC 9421 HTTP Message Signatures, OAuth 2.0 / OIDC), those additions are explicitly marked as industry supplements.

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
2. Add `SKILL.md` with lowercase hyphenated `name` and third-person `description` frontmatter, keeping the main file concise (~150–250 lines).
3. Split deep chapter/topic references into `references/` and link them via relative Markdown paths from `SKILL.md`.
4. Separate book-canonical conventions from any high-certainty industry supplements so readers know what comes from the source text vs. broader standards.
5. Update the **Included Skills** table above.
