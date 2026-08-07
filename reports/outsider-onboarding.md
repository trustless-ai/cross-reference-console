# Outsider onboarding report: walking the Cell path from zero

This report follows the instruction in [PR #11 comment](https://github.com/trustless-ai/agent-sdk/pull/11#issuecomment-2788515199): read NODES.md and CELL-v2.md, attempt to walk the path as an outsider, and note where it breaks.

**Date:** 2026-08-07
**Author:** M Zidan Fatonie (external node candidate, Bastion CAPV maintainer)
**Target claim:** A Bastion verdict routed through CAPV (ERC-8354)

---

## What worked

### Spec clarity where it matters

The registry identity derivation is documented and checkable. Running `python3 reference/registry_id.py` produces `sha256:9b871ba9cf05e9da7df78e0b15d44fc04059e6af4bda8037d6f456984598d157` which matches the constant in CELL-v2.md. The claim_id derivation through JCS is equally reproducible.

The signature grammar section (CELL-v2.md, section 3) is precise. Hexadecimal encoding rules are explicit for both EIP-712 and Nostr lanes. The note about the `0x` prefix divergence between eth_account and ethers shows this was hard-won and well captured.

The validation tool (`reference/validate_cell.py`) works. You can feed it a cell file and it performs all mechanical checks. This gives an outsider a clear target.

The append-only discipline (frozen v0, frozen v1, never re-sign history) is consistent across the entire codebase. Every version migration is documented and mechanically checkable via activation commit hashes.

### Concepts that translated well

The idea of mutually recomputable cells is clear. The matrix shape (rows of cells across nodes, each independently produced) is understandable from CELL.md alone. The claim neutrality rule (registry_id stays in Cell layer, never in ClaimPreimage) is well motivated.

---

## Where the path breaks for an outsider

These are ordered by the sequence an outsider follows when attempting to walk the path.

### Gap 1: No create tool, only a validate tool

`reference/validate_cell.py` checks an existing cell. There is no `sign_cell.py` or `create_cell.py` that produces a cell from a claim preimage and a key.

An outsider must:
1. Read CELL-v2.md for the EIP-712 type definitions
2. Read the v2 domain specification (name, version, chainId, salt)
3. Implement EIP-712 signing from scratch
4. Hope that the signature grammar in section 3 is the only trap

A `create_cell.py` script similar to validate_cell.py would solve this. It would take a claim_preimage, a verifier key, and evidence as input, then produce a signed cell file ready for validation.

### Gap 2: No step by step onboarding document

NODES.md says "one PR adding one object to nodes in nodes.json" and describes the cell delivery contract. It never walks through the sequence:

1. Obtain a verifier identity
2. Define your lane
3. Register a node (the nodes.json PR)
4. Find a claim to cross-verify
5. Recompute it
6. Create and sign a cell
7. Validate it with the tool
8. Submit the cell (PR or self-host)

Every step after "read the spec" is undocumented. The four current nodes were built by spec authors who share context. An outsider has none of that context.

### Gap 3: The lane taxonomy is undefined

nodes.json lists four lanes:
- `attestation/invinoveritas`
- `recompute/cross-reference-console`
- `recompute/receiptos`
- `recompute/mycelium`

There is no document defining what a lane is, how to name one, or what makes a lane valid. The pattern appears to be `category/implementation` but this is never stated. An outsider defining `zk/capv` or `recompute/bastion` would be guessing.

Suggested fix: a LANES.md document defining the lane namespace, the two categories (attestation, recompute), and what a new lane requires to be accepted.

### Gap 4: No verifier identity available yet

nodes.json verifiers are either ERC-8004 token ids (node 1: `54848`) or on-chain attestor addresses (nodes 2 through 4: `0x...`). The `BastionConfidentialGate.sol` contract is not deployed on any network. Without a deployed contract, there is no address. Without an address, there is no verifier field. Without a verifier field, you cannot register.

This is not a spec bug. It is the honest blocker TMerlini acknowledged: "until it lands, a Bastion verdict is not independently checkable." The question is whether the spec should document what a pending node does while waiting for deployment. Even a section called "Pre deployment node registration" listing requirements to be met before the PR would help.

### Gap 5: Claim intake is closed-loop

The only claim source is `invinoveritas-ledger`. The admission mechanism described in NODES.md section on intake was "ledger-only by group decision (2026-08-05)."

An outsider cannot produce a cell for a claim that does not exist. To produce a cell for a Bastion verdict, either:
- The invinoveritas ledger must accept a Bastion-related submission
- A new claim source must be added to nodes.json
- The spec must document how an outsider introduces a claim into the system

The current system works for the four nodes because they all consume claims from the same ledger. An outsider needs a documented intake path.

### Gap 6: CELL-v2.md is a diff, not a standalone document

CELL-v2.md explains what changed from v1 (registry_id binding, signature grammar). It assumes the reader already knows:
- The full cell format from v0 and v1
- The evidence structure
- The independence evidence format
- The result semantics (GREEN, RED, AMBER)
- The edge rule (2 or more GREEN on distinct lanes)

An outsider must triangulate three documents (CELL.md v0, CELL-v1.md, CELL-v2.md) to understand the complete format that a new cell must follow. A single CELL.md that is the in-force spec (with appendix sections for frozen history) would be easier to follow.

### Gap 7: Self-hosted cell URL is not documented

Node 2 self-hosts via GitHub raw URLs as defined in `cell_url_template`. There is no documentation of what the endpoint must return, what content type it must serve, how CI fetches it, or what happens when it is unreachable (AMBER discipline is mentioned but not documented).

---

## Concrete suggestions

| # | Gap | Suggestion |
|---|---|---|
| 1 | No create tool | Add `reference/create_cell.py` that takes claim_preimage, key, and evidence, and outputs a signed cell |
| 2 | No onboarding doc | Add `ONBOARDING.md` with step-by-step walkthrough for a new node operator |
| 3 | Lane taxonomy | Add `LANES.md` defining lane namespace, categories, and acceptance criteria |
| 4 | No verifier id | Document pre-deployment node registration: requirements, staging, what a pending entry looks like |
| 5 | Closed intake | Document how an outsider introduces a claim, or open a second claim source |
| 6 | CELL-v2 as diff | Produce a unified CELL.md containing the current in-force spec with frozen-history appendices |
| 7 | Self-host docs | Document the cell endpoint contract: URL pattern, response format, CI interaction |

---

## What I was able to complete

- Derived registry_id and verified it matches the constant
- Read and understood the full cell format across v0, v1, and v2
- Ran `validate_cell.py` against existing cells to confirm the tool works
- Identified the EIP-712 domain and type definitions needed for signing

## What I could not complete

- Register a node (no verifier address from an undeployed contract)
- Introduce a Bastion claim (no intake path)
- Create and sign a cell (no claim to reference, no create tool)
- Run a cell through CI (no node entry, no cell to submit)

---

## Summary

The spec is internally consistent. The registry identity, claim derivation, and signature verification are documented with precision. The break points are all around the edges: tooling for outsiders, the lane taxonomy, the intake path, and the absence of a verifier identity from an undeployed contract. None of these are spec bugs. They are the gap between "four spec authors can follow this" and "a stranger can follow this."

The recommendation: ship ONBOARDING.md and LANES.md first (low effort, high signal). The create tool can follow. The Bastion cell path is blocked by contract deployment, not by documentation.