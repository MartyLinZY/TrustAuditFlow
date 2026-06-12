# CCF-A Style Self-Review

Date: 2026-06-12

Scope: This review checks the current anonymous English draft against common expectations for CCF-A-level systems/security/data-management papers. It is not a venue-specific compliance check. A strict check still requires selecting the exact target venue and template.

## Tool Checks

- Anonymous source check: passed.
  - `main.tex` uses `\author{}`.
  - No Chinese author name, affiliation, local username, GitHub URL, or Chinese characters remain under `paper/TrustFlowAudit_IEEE_Paper`.
- English-only paper check: passed.
  - `rg "[\p{Han}]" paper/TrustFlowAudit_IEEE_Paper` returns no paper-text hits after README conversion.
- PDF build check: passed.
  - `build/main.pdf` was generated successfully with Tectonic.
  - PDF has 6 pages.
  - PDF text extraction shows no author or affiliation on the title page.
- Build warnings:
  - Font substitution warnings under Tectonic.
  - A few underfull hbox warnings in a table and paragraphs.
  - These are polish issues, not blocking logic issues.

## Overall Verdict

Verdict: not ready for CCF-A submission.

Reason: the draft is now anonymous and English, and the problem framing is much clearer, but it is still a design-position paper without the experimental evidence, formal security argument, verified bibliography, and venue-specific compliance normally expected by CCF-A venues.

## Top Blocking Issues

1. Missing evaluation section.
   - Current paper explicitly says evaluation is deferred.
   - CCF-A-level systems/security papers normally need quantitative results, baselines, ablations, and reproducibility details.
   - Required next step: add experiments comparing at least BLoP-style full-node PBFT, Merkle batch anchoring, committee confirmation, and TrustAuditFlow full path.

2. Bibliography is improved but not submission-grade.
   - Current `references.bib` entries were exported from the local Zotero library and local `file` paths were removed.
   - The BLoP paper was not found in Zotero, so its placeholder BibTeX entry was removed from the draft.
   - Required next step: import the BLoP paper into Zotero, export it through the same workflow, and verify all citations against DBLP, ACM DL, IEEE Xplore, USENIX, Springer, or publisher pages.

3. Method is not yet reproducible enough.
   - The current design defines components and equations, but lacks algorithm blocks, protocol messages, parameter tables, failure-handling pseudocode, and complexity analysis.
   - Required next step: add algorithms for committee selection, batch anchoring, sampled audit, recovery, trust update, and fallback.

## Top Polish Issues

1. Venue template is generic IEEE-style, not a confirmed CCF-A venue template.
   - IEEEtran may fit some IEEE-style venues but not ACM CCS, USENIX Security, SIGMOD, NSDI, OSDI, or other CCF-A venues.
   - Required next step: choose the target venue before final formatting.

2. Table and figure density need improvement.
   - The BLoP-vs-TrustAuditFlow table is narrow and produces underfull hbox warnings.
   - Required next step: simplify table text or use a full-width table if the venue allows it.

3. The contribution is plausible but still modest.
   - Current novelty is a system integration and lightweight upgrade path.
   - Required next step: sharpen what is new compared with existing blockchain auditing, committee consensus, and erasure-code storage papers.

## Claim Audit

Claim: TrustAuditFlow is a lightweight extension of BLoP rather than a replacement.
Verdict: keep.
Evidence used: current framing in abstract, introduction, method, and conclusion.
Missing evidence: exact BLoP paper metadata and detailed BLoP mechanism citation verification.
Overclaim risk: low.
Suggested wording: keep the current "extension" and "fallback" wording.

Claim: Routine audit events can be confirmed by a trusted committee to reduce cost.
Verdict: weaken until experiments are added.
Evidence used: design analysis only.
Missing evidence: measured confirmation delay, chain record count, communication overhead, and security sensitivity under committee compromise.
Overclaim risk: medium.
Suggested wording: "is designed to reduce" or "is expected to reduce" before evaluation.

Claim: Erasure-code-assisted recovery closes the audit loop.
Verdict: keep as a design claim, not as a measured result.
Evidence used: method section explains recovery threshold and commitment update.
Missing evidence: real Reed-Solomon implementation, corruption ratios, recovery success rate, and runtime overhead.
Overclaim risk: medium.
Suggested wording: "connects audit failure with a recovery procedure" rather than "guarantees recovery".

Claim: The current draft is CCF-A ready.
Verdict: remove.
Evidence used: no evaluation section; citations unverified.
Missing evidence: experiments, verified references, formal comparison, target-venue formatting.
Overclaim risk: high.
Suggested wording: "The draft has a clearer CCF-A-oriented structure but is not submission-ready."

## Section Checklist

- Abstract: partially pass.
  - Problem and method are clear.
  - Results are intentionally absent, which is a CCF-A blocking issue.
- Introduction: pass for framing.
  - Research question and gap are now explicit.
  - Contribution list is concrete and avoids empirical overclaiming.
- Related Work: partial pass.
  - Covers PDP/PoR, blockchain auditing, erasure coding, consensus, and BLoP.
  - Needs deeper comparison and verified citations.
- Problem Formulation: pass for current stage.
  - Baseline, system problem, threat model, and design goals are explicit.
  - Needs stronger formalization for submission.
- Method: partial pass.
  - Architecture and workflow are understandable.
  - Needs algorithms, protocol messages, parameter tables, and complexity analysis.
- Evaluation: fail.
  - Not written yet.
- Discussion: pass.
  - Limitations are clearly stated.
- Conclusion: pass for draft stage.
  - Does not overclaim empirical results.

## Required Next Revision

1. Select the target venue.
2. Convert to the exact venue template and anonymity policy.
3. Verify all references and import the BLoP paper into Zotero before citing it.
4. Add algorithms and complexity analysis.
5. Add evaluation with baselines, ablations, metrics, and reproducibility notes.
6. Add artifact/ethics/open-science statements if required by the target venue.
