# Part 1 & 2: Design Principles (Chapters 1–5)

Covers naming, resource scope and hierarchy, and data types/defaults.

---

## Chapter 3: Naming

### Core Quality Criteria
- **Expressive:** Unambiguously conveys what a resource, method, or field is.
- **Simple:** Short and jargon-free without sacrificing clarity (avoid verbose `UserAccountProfileInformationEntity`, prefer `User`).
- **Predictable:** Consistent vocabulary and structure across the entire API so users guess right on the first try.

### Language, Grammar, and Syntax
1. **Language:** Always use **American English** (`color`, `canceled`, `catalog`) for API identifiers (resources, methods, fields), regardless of team location; localize only human documentation if needed.
2. **Imperative Actions:** Methods/RPCs must use **imperative mood** (`CreateBook`, `ArchiveEmail`, `GetValidationErrors`), never indicative questions (`isValid()` leaves callers guessing whether it is local vs. remote and whether it returns `boolean` or error details).
3. **Prepositions Are an API Smell:** Names containing `with`, `for`, `by`, or `to` (e.g., `ListBooksWithAuthors`) signal a missing pattern—usually `FieldMask` / view expansion, filtering, or an association resource. (Rare domain unit exceptions like `bitsPerSecond` are fine.)
4. **Singular vs. Plural:**
   - Resource types and singular reference fields: **singular** (`Book`, `Author`, `favoriteBook`).
   - URL collections: **plural** using proper American English irregulars (`/books/123`, `/people/456`, `/feet/7`, `/octopuses/8` — never naive `+ "s"`).
5. **Casing Consistency:** Pick one convention per specification format and never mix:
   - OpenAPI / JSON / TypeScript: `UpperCamelCase` for interfaces/types (`UserSettings`), `camelCase` for fields (`firstName`) and URL collection paths (`/chatRooms`), `UpperCamelCase` for RPC names (`CreateChatRoom`).
   - Protobuf: `UpperCamelCase` for messages/RPCs, `snake_case` for fields (`first_name`).
6. **Avoid Reserved Keywords:** Never name fields after common language keywords (`from`, `to`, `class`, `type` when avoidable—e.g. prefer `sender`/`recipient` or `payer`/`payee`).

### Context & Units (Mars Climate Orbiter Rule)
- **Use surrounding context, don't duplicate it:** Inside `ChatRoom`, use `title`, not `chatRoomTitle`.
- **Beware misleading context:** `size` on `AudioClip` vs. `Image` is ambiguous (bytes? duration? pixels?).
- **Always encode units in primitive names—or use a richer type:**
  - Primitive: `sizeBytes`, `sizeMegapixels`, `delaySeconds`, `impulseNewtonSeconds` (never bare `size`, `delay`, `timeout`, `impulse`).
  - Better for composite values: instead of `dimensionsPixels: "1024x768"`, define `{ lengthPixels: number; widthPixels: number }`.
  - Distinguish binary vs. decimal prefixes explicitly (`sizeGb` vs. `sizeGib`).

---

## Chapter 4: Resource Scope and Hierarchy

### Relationship Types
1. **Inline Data:** Nested object/array stored directly inside a parent resource.
2. **Cross-Reference:** Pointer field (`authorId: string`) referencing another top-level or sibling resource.
3. **Parent-Child Hierarchy:** Ownership path (`chatRooms/{room}/messages/{msg}`).
4. **Many-to-Many:** Modeled via Association Resource (`Membership`) or `:add`/`:remove` custom methods (see [03-resource-relationships.md](./03-resource-relationships.md)).

### Decision Guide
1. **Do you need a relationship at all?** Every relationship carries long-term consistency, permission, and deletion costs (e.g., celebrity fan-out on `User` followers). Only model relationships essential to the API's core goal.
2. **Inline data vs. Reference (`*Id`)?**
   - **Inline** when the sub-concept is small, bounded, 1:1 or tightly owned, and almost always read with the parent (e.g., `BoundingBox` on `Annotation`).
   - **Reference (`*Id`)** when the target is shared across many parents (`Author` written multiple `Book`s), large, updated independently, or has different ACLs.
3. **Hierarchy (`parents/{p}/children/{c}`) vs. Top-Level + Reference?**
   - Use **Hierarchy** ONLY when there is **true ownership**:
     - Deleting parent cascades to delete children.
     - Access control on parent inherits down to children.
     - Children **never move** between parents (`Page` inside `Book` = good hierarchy; `Book` on `Shelf` = bad hierarchy because books move shelves—use `shelfId` instead).

### Three Resource Layout Anti-Patterns
1. **Resources for everything:** Turning value objects (`BoundingBox`, `Point`) into full CRUD resources multiplies endpoints without benefit. Keep non-independently-addressed concepts as inline data types.
2. **Deep hierarchies:** Nesting `universities/{u}/schools/{s}/courses/{c}/semesters/{sem}/documents/{d}` forces callers to track 4+ parent IDs and blocks flexible queries. Flatten intermediate groupings (`schools`, `semesters`) into reference/filterable attributes to keep paths ≤ 2–3 levels.
3. **In-line everything:** Denormalizing shared entities (`Author` details copied inside every `Book`) creates update anomalies and ambiguity over which copy is canonical.

---

## Chapter 5: Data Types and Defaults

### Missing (`undefined`) vs. `null` vs. Zero Value
Serialization formats vary: JSON supports `null` and omitted keys (`undefined`), while formats like Proto3 collapse missing/zero primitives.
- **Explicit rule:** Always define and document distinct semantics for:
  1. Present value (`"red"`),
  2. Empty/zero value (`""`, `0`, `false`, `[]`, `{}`),
  3. Explicit `null` (typically "clear this field" or "explicitly unset"),
  4. Missing/omitted key (in `PATCH`: "do not touch"; in `Create`: "apply server default").

### Booleans
- **Use positive naming:** `allowChatbots`, `enableLogging`, `archived` — avoid double negatives like `room.disallowChatbots === false`.
- **Avoid proliferation of boolean flags:** If participant roles will grow (`allowModerators`, `allowGuests`, `allowBots`), use a richer field/collection instead of N booleans.
- Only invert to negative naming as a last resort in zero-value-only formats (like legacy Proto3 without presence) where `false` must mean "allowed by default" — knowing this locks the default forever.

### Numbers
- **Never use numeric types for IDs** (you don't do arithmetic on IDs; use strings).
- **Always document bounds** (`min`, `max`, bit width); internally prefer signed 64-bit integers (`int64`) for whole numbers unless a smaller bound is guaranteed.
- **Never use `0` as a sentinel for "use default"** when `0` is a valid domain value.
- **JSON precision trap (IEEE-754):** JavaScript `Number` loses integer precision above $2^{53} - 1$ (`9007199254740991`) and suffers binary float rounding (`0.1 + 0.2 === 0.30000000000000004`).
  - **Rule:** Serialize 64-bit integers and arbitrary-precision decimals / currency amounts as **strings** (`"0.1"`, `"9999999999999999999"`), never raw JSON numbers.

### Strings
- **Bounds:** Specify max length in characters/Unicode code points; budget storage at worst-case 4 bytes/char (UTF-32) when sizing DB columns.
- **Reject, never silently truncate** inputs exceeding max length (`400 Bad Request`).
- **Encoding & Normalization:** Standardize on **UTF-8**. Normalize strings—and **strictly require Unicode Normalization Form C (NFC)** (or ASCII-only) for any identifier or map key so visually identical strings (`é` precomposed vs. `e` + combining accent) never collide or miss lookups.

### Enumerations
- **Avoid rigid schema enums in web APIs.** Integer-backed enums obscure logs (`eyeColor: 2`), and closed enums break older clients whenever the server adds a new value.
- **Rule:** Use **string** fields validated server-side against documented values (or standard vocabularies like MIME types `"application/pdf"`).

### Lists (Arrays)
- **Lists are atomic:** Clients replace the entire array (`book.categories = [...]`). Never expose index-based patching (`items[2]`) or parallel item-mutation endpoints that race with full-array updates.
- **Homogeneous types only:** Never mix strings and numbers in the same array.
- **Always bound list size** (max item count + max item size) and reject overflow. If an array can grow unboundedly, promote it to a **sub-collection of resources** (with pagination).

### Maps (`Map<string, V>`)
- Use **interfaces (custom data types)** for known, fixed schemas (`SecurityConfig`), and **maps** only for dynamic, instance-specific keys (`ingredientAmounts`, `labels`).
- **Keys must be UTF-8 NFC strings** (never numbers).
- **Bound both entry count and per-key / per-value lengths** (e.g., keys ≤ 100 chars, values ≤ 500 chars); avoid unbounded total-character budgets that invite stuffing blobs into maps.
- Unlike lists, `{}` (empty map) and `null` (use default) are cleanly distinguishable in JSON.

---

## Industry Supplements (>90% Confidence)

*Beyond the book's core chapters, apply these standard representations consistently:*
- **Timestamps:** Serialize as RFC 3339 / ISO 8601 UTC strings (`"2026-11-25T03:00:00Z"`), naming timestamp fields with `*Time` suffix (`createTime`, `updateTime`, `expireTime`).
- **Money / Currency:** Represent either as decimal string + ISO 4217 code (`{ amount: "19.99", currencyCode: "USD" }`) or Google-style `{ currencyCode: "USD", units: "19", nanos: 990000000 }`.
- **Languages & Locales:** Use IETF BCP 47 strings (`"en-US"`, `"ja-JP"`), not custom enums.
