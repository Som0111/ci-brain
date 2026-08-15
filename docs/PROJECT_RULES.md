# Claude Code Project Execution Rules

## Core Principles

- **No timeline-based roadmap.** Progress is phase-driven, not date-driven. A phase ends when its checklist is complete.
- **Token efficiency is a priority.** Use Claude tokens only for meaningful implementation, debugging, architecture, testing, review, and necessary documentation. Avoid unnecessary artifacts, repetition, decorative output, or random/irrelevant work.
- **Minimum human interaction.** Claude should inspect, implement, test, diagnose, and self-correct wherever possible. Ask the human only when a genuine judgment or decision is required.
- **Human ownership.** The project should not feel like generic AI-generated work. Keep clearly marked sections where the human can add/edit their own wording, decisions, observations, or interpretation. Never fabricate human work or observations.

## Phase Structure

Every major phase must be divided into **subphases**.

### Subphase limit
- Each subphase must target a maximum of **20 minutes of Claude Code work**.
- If a task is likely to exceed 20 minutes, split it into smaller, independently verifiable subphases.
- Avoid long uninterrupted Claude Code sessions because they waste tokens.

### Phase checklist
Each phase must have its own checklist covering:
1. Implementation
2. Tests
3. Integration/regression checks
4. Bug detection and self-correction
5. Documentation update
6. Final verification

A phase is complete only when its checklist passes.

## Self-Review / Auto-Correction

At the end of every phase, Claude must:
1. Compare the implementation against the phase requirements.
2. Inspect relevant files for unfinished or inconsistent work.
3. Run appropriate tests/checks.
4. Identify bugs, regressions, and missing requirements.
5. Fix issues it can resolve independently.
6. Re-run relevant tests after fixes.
7. Update the phase checklist.
8. Stop only when verified or when a genuine human decision is required.

Do not make the human perform routine verification that Claude can perform itself.

## Token Usage

Prioritize tokens for:
- Core implementation
- Architecture decisions
- Debugging
- Tests and integration
- Code review
- Important documentation

Avoid:
- Unnecessary artifacts
- Decorative documentation
- Excessive narration
- Repeating established information
- Random or irrelevant output
- Work that does not materially improve the project

When multiple approaches work, prefer the one with less complexity and lower token usage.

## Humanization

Claude should:
- Use concise, practical, natural documentation.
- Avoid generic AI-style filler.
- Leave clearly marked **Human Edit** sections where useful.
- Highlight areas where the human should add their own wording, decisions, observations, or interpretation.
- Preserve genuine human ownership rather than trying to conceal AI involvement.

## Human Explanation File

Maintain one separate file:

`DEVELOPER_GUIDE.md`

It must concisely contain:
- What the project does
- Why major components exist
- Important architecture/design decisions
- How the main pipeline works
- How to run and test the project
- Important commands
- Known limitations
- What changed in each completed phase
- What the human should understand, edit, or review
- Important troubleshooting notes

### Auto-update rule
At the end of **every completed phase**, Claude must update `DEVELOPER_GUIDE.md` before marking that phase complete.

Do not create separate explanation artifacts unless genuinely necessary. Keep human-facing knowledge consolidated in `DEVELOPER_GUIDE.md`.

## Standard Workflow

`Phase → Subphases (≤20 min each) → Implement → Test → Self-review → Fix → Re-test → Update checklist → Update DEVELOPER_GUIDE.md → Complete`

The roadmap is **phase-based and adaptive**, not time-based. Phases may finish early or be expanded when implementation complexity genuinely requires it.
