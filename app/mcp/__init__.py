"""MCP gateway: front many upstream MCP servers behind one governed endpoint.

The gateway is an MCP *server* to its clients (POST /mcp) and an MCP *client* to
the upstream servers (app/mcp/client.py). Every LLM-gateway pillar maps 1:1 —
registry, virtual-key scoping, usage ledger — so this module is built by analogy
with the model-routing side, not from scratch.
"""
