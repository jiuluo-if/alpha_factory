# Documentation by question

Start with the root [`AGENTS.md`](../AGENTS.md), then read
[`ARCHITECTURE_AGENT.md`](ARCHITECTURE_AGENT.md) and
[`wqb_agent/research_api.py`](../wqb_agent/research_api.py). Do not recursively
read every document.

| If you need to… | Read… |
|---|---|
| understand the agent-facing model | [`ARCHITECTURE_AGENT.md`](ARCHITECTURE_AGENT.md) |
| understand BRAIN endpoints, response truth, Retry-After, or capability status | [`BRAIN_PROTOCOL.md`](BRAIN_PROTOCOL.md) |
| discover valid operators and field types | [`OPERATORS_CHEATSHEET.md`](OPERATORS_CHEATSHEET.md) |
| understand allowed Simulation settings | [`SIMULATION_SETTINGS.md`](SIMULATION_SETTINGS.md) |
| design a falsifiable experiment and interpret evidence | [`RESEARCH_POLICY.md`](RESEARCH_POLICY.md) |
| understand current research spaces and selection context | [`EXPLORATION_ROADMAP.md`](EXPLORATION_ROADMAP.md) |
| recover or audit local research state | [`STATE_LAYOUT.md`](STATE_LAYOUT.md) |
| understand search heuristics and trial accounting | [`SEARCH_POLICY.md`](SEARCH_POLICY.md) |
| understand file naming and derived-output boundaries | [`FILE_ORGANIZATION_AND_NAMING.md`](FILE_ORGANIZATION_AND_NAMING.md) |
| check environment/tool discipline | [`DSH_TOOL_DISCIPLINE.md`](DSH_TOOL_DISCIPLINE.md) |

## Historical reference

`PHASE*.md` and `superpowers/**` document earlier design decisions or completed
work. They are historical reference. Do not treat them as current runtime
policy unless the current code explicitly depends on them.

Reports, round summaries, and current experiment status are derived or live
state; consult `.wqb_state/` and current BRAIN responses according to the
rules in `AGENTS.md`.
