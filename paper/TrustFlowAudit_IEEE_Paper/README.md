# TrustAuditFlow IEEE-Style Anonymous Draft

This directory contains an anonymous English LaTeX draft for:

> TrustAuditFlow: A Lightweight Extension of BLoP for Blockchain-Based Distributed Data Verification in Data Circulation

## Structure

- `main.tex`: IEEE two-column main file.
- `references.bib`: bibliography entries. Bibliographic metadata still needs venue-level verification before submission.
- `sections/`: section files.
- `build/`: generated compilation outputs.

## Current Scope

Completed in this draft:

- Anonymous title block
- Abstract and keywords
- Introduction
- Related work
- Problem formulation and design goals
- System model
- TrustAuditFlow design
- Security and cost analysis
- Discussion and future work
- Conclusion

Not yet completed:

- Evaluation section
- Experimental results
- Ablation study
- Quantitative comparison with baselines
- Venue-specific formatting and artifact appendix

## Build

Use `pdflatex` or `latexmk`:

```bash
cd paper/TrustFlowAudit_IEEE_Paper
latexmk -pdf -bibtex -interaction=nonstopmode -output-directory=build main.tex
```

Manual build:

```bash
pdflatex -output-directory=build main.tex
bibtex build/main
pdflatex -output-directory=build main.tex
pdflatex -output-directory=build main.tex
```
