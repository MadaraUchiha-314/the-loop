"""The ingress adapters: one per provider transport (issue-496, R1, R7).

Each adapter turns a provider delivery into an :class:`~the_loop.gateway.envelope.Envelope`
and calls ``store.append`` **before** answering the provider (R2.4). The shared halves —
which work item a payload names and which key makes two transports' copies one event —
are :mod:`.common`.
"""
