"""Domain-neutral core: register specs, schema loading, validation and evidence checks.

Core modules never import from ``knowledge_automata.domains`` (ADR-0009). Callers pass a
``RegisterSpec`` instead.
"""
