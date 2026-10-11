# Sourced before each verifier whose command has "env_file": true. It holds no secret.
# The server already strips provider keys and secret-like names from the environment.
unset OPENAI_API_KEY OPENAI_API_KEY_OP_REF ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN CODEX_API_KEY
export CI=1 PYTHONDONTWRITEBYTECODE=1 DO_NOT_TRACK=1 E2E_TELEMETRY_DISABLED=1
