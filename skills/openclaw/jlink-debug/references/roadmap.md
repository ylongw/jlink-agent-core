# jlink-debug roadmap

## Near-term

- Add board profile support (`--profile` YAML)
- Add per-SN lock file (`/tmp/jlink-lock-<sn>`) to prevent multi-agent contention
- Add better `gdbserver-stop` filtering by port/SN

## Mid-term

- Build + flash + RTT unified command (`run`)
- Structured error codes (`ERR_TOOL_MISSING`, `ERR_PROBE_BUSY`, `ERR_FLASH_FAIL`)
- Retry strategy templates for flaky RF tests

## Long-term

- Adapter wrappers for OpenClaw, Claude Code, Codex CLI
- CI-ready dry-run mode for scripts
- Community board profile registry
