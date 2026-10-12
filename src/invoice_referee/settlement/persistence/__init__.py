"""Persistence layer: SQL lifecycle functions over an open connection.

Each function takes an already-open ``sqlite3.Connection`` (plus ``artifact_root``
where a file is needed). The ``Store`` façade owns the connection/transaction
boundary, so every financial check and write stays atomic inside one
``BEGIN IMMEDIATE``. Nothing here opens its own connection, commits, or calls
back into the façade.

Modules:
- ``sqlite_records``: common record helpers/serialization (no policy).
- ``queries``: read projections + governing selector + money-context rebuild.
- ``decision_records``: presentation/decision writes.
- ``money_records``: money-event writes + revalidation.
- ``action_records``: handoff/closure/adjustment writes.
- ``advance_records``: B3/B5 advance lifecycle.
- ``linked_context_records``: B6→B7 child/declaration/company-context.
"""
