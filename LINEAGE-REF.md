# LineageRef — implementation lineage reference grammar (v0)

**Status:** Normative companion to [CELL-v3.md](CELL-v3.md).  
**Scope:** Syntax of each `string` element in `evidence.independence.derived_from`.

---

## 1 · Purpose

Each LineageRef names an **implementation** that the signing node declares as a lineage source. LineageRefs are **signed provenance** — they are not, by themselves, proof that derivation occurred.

The gate validates **syntax only**. **Resolution** (matching refs to implementations in the registry) happens at independence-evaluation time and may yield **INDEPENDENCE_NOT_PROVEN** without invalidating the Cell.

---

## 2 · Grammar (normative)

Every element of `derived_from` MUST match **exactly one** of:

### 2.1 · Implementation hash ref (preferred)

```
crc.lineage.v0:impl/sha256:<64-lowercase-hex>
```

Example:

```
crc.lineage.v0:impl/sha256:abc123def4567890abc123def4567890abc123def4567890abc123def4567890
```

### 2.2 · Repo snapshot ref

```
crc.lineage.v0:repo/<url>#commit/<40-hex>#path/<url-encoded-path>
```

- `<url>` — repository URL as signed (HTTPS preferred).
- `<40-hex>` — git commit object id, lowercase.
- `<url-encoded-path>` — path within repo, percent-encoded per RFC 3986.

Example:

```
crc.lineage.v0:repo/https://github.com/example/recompute#commit/a1b2c3d4e5f6789012345678901234567890abcd#path/reference%2Fclaim_id.py
```

### 2.3 · Rejected forms

| Form | Gate result |
|---|---|
| Bare URL without prefix | **REJECT** |
| `null`, empty string | **REJECT** (use `[]` on the array, not empty elements) |
| Duplicate elements in array | **REJECT** |
| Ref resolving to signer's own `impl_hash` | **REJECT** |

---

## 3 · Resolution (evaluator semantics)

Resolution is **not** a gate check. Evaluators MUST:

1. Parse each LineageRef per §2.
2. Search **registry Cells on the same `claim_id`** for a matching implementation:
   - `impl/sha256:…` → match `evidence.independence.implementation.impl_hash` (normalize `sha256:` prefix).
   - `repo/…#commit/…#path/…` → match `(repo, commit, path)` on `implementation`.
3. If no match: mark **unresolved**; pairs involving this Cell → **INDEPENDENCE_NOT_PROVEN**.
4. If match: load matched Cell's `derived_from` for transitive closure ([CELL-v3.md §4](CELL-v3.md)).

### 3.1 · Cross-claim resolution

**[PENDING-VECTOR]** — Default: same-claim only. Cross-claim refs require explicit future prefix or registry catalog; do not assume until vector lands.

---

## 4 · Empty `derived_from` array

`derived_from: []` is **not** a LineageRef. It declares **no known derivation from another implementation** ([CELL-v3.md §1.1](CELL-v3.md)). It MUST NOT be interpreted as mechanically proven independence.

---

## 5 · Examples (non-normative)

**Independent declaration (spec-derived):**

```json
"derived_from": []
```

**Single-parent fork:**

```json
"derived_from": [
  "crc.lineage.v0:impl/sha256:abc123def4567890abc123def4567890abc123def4567890abc123def4567890"
]
```

**Multi-parent:**

```json
"derived_from": [
  "crc.lineage.v0:repo/https://github.com/a/impl#commit/aaa…#path/tools%2Fx.py",
  "crc.lineage.v0:repo/https://github.com/b/impl#commit/bbb…#path/ref%2Fy.py"
]
```
