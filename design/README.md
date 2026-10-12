# System Design & Architecture

This directory enforces system integrity through a two-file bicameral contract: `SPEC.md` provides the authoritative human-readable specification (rules, lifecycles, and domain logic for teammates and deliverables), while `contracts.py` provides the machine-executable formal specification (types, state transition invariants, and validation rules). Any architectural change requires updating both files simultaneously, allowing agents and developers to programmatically verify that the written prose and executable constraints remain in perfect synchronization.
