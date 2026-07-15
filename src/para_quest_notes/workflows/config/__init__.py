"""``pqn-config`` — read-only effective-config inspector (no LLM).

Reports the tool configuration a ``pqn-*`` run will actually use, with
provenance for each value (built-in default vs ``config.yaml`` vs env vs
flag) and which vault-discovery rung won. The read-only complement to the
write workflows: answers "what config will you run with, and why?"
without the caller having to infer it from workflow output.

Read-only by design. There is no ``set`` counterpart — edit
``config.yaml`` by hand.
"""
