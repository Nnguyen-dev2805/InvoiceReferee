"""Provider boundary (T05): OCR transport, per-document analysis, cross-source.

This package owns the OCR/Kimi adapters and the contract validator. Adapters
return sourced facts and proposals only — never a final business action; the
deterministic evaluators (T03) decide.
"""
