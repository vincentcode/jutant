"""The banking domain: what staff ask about, whichever of the bank's systems holds it.

The MCP tools call these services; the services call the bank's systems through the ports in
`packs.banking.adapters.base`. A new system is a new adapter, not a change here or in the tools.
"""
