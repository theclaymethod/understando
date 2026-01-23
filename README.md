# Understando

A Claude Code skill + hook that quizzes you on your code changes before allowing commits.

## Why?

When using AI to write code, it's easy to commit changes you don't fully understand. Understando ensures you comprehend what's being committed by asking quiz questions about the staged changes.

## Features

- **Difficulty levels**: Easy, Medium, Hard - choose your challenge
- **Mixed question types**: Multiple choice and free-text answers
- **LLM-judged responses**: Free-text answers evaluated for understanding, not exact matches
- **Explanations**: Learn from wrong answers with detailed explanations
- **Configurable**: Adjust question count, default difficulty, and pass threshold
- **Skippable**: Type "skip" if you really need to bypass (with a gentle shame message)

## Installation

### Quick Install (Skill Only)

```bash
npx add-skill claytonkim/understando
```

This installs the skill. To enable automatic quiz on commits, you also need the hook (see below).

### Full Install (Skill + Hook)

#### Option A: Install Script

```bash
git clone https://github.com/claytonkim/understando.git /tmp/understando
/tmp/understando/install.sh
rm -rf /tmp/understando
```

#### Option B: Manual Installation

1. **Install the skill:**
   ```bash
   npx add-skill claytonkim/understando
   ```

2. **Copy the hook:**
   ```bash
   mkdir -p .claude/hooks
   curl -o .claude/hooks/understando-gate.sh \
     https://raw.githubusercontent.com/claytonkim/understando/main/hooks/understando-gate.sh
   chmod +x .claude/hooks/understando-gate.sh
   ```

3. **Register the hook** in `.claude/settings.json`:
   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Bash",
           "hooks": [
             {
               "type": "command",
               "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/understando-gate.sh"
             }
           ]
         }
       ]
     }
   }
   ```

4. **(Optional) Add config** - copy to project root:
   ```bash
   curl -o .understando.json \
     https://raw.githubusercontent.com/claytonkim/understando/main/understando.json
   ```

### Global Installation

To install globally (all projects):

```bash
# Skill
npx add-skill claytonkim/understando -g

# Hook (manual - add to ~/.claude/settings.json)
mkdir -p ~/.claude/hooks
curl -o ~/.claude/hooks/understando-gate.sh \
  https://raw.githubusercontent.com/claytonkim/understando/main/hooks/understando-gate.sh
chmod +x ~/.claude/hooks/understando-gate.sh
```

## Configuration

Create `.understando.json` in your project root:

```json
{
  "default_questions": 5,
  "default_level": "medium",
  "pass_threshold": 0.8
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_questions` | number | 5 | Number of quiz questions |
| `default_level` | string | "medium" | Default difficulty (easy/medium/hard) |
| `pass_threshold` | number | 0.8 | Percentage required to pass (0.0-1.0) |

## Usage

### With Hook (Automatic)

Just commit as normal through Claude Code:

```
> commit these changes
```

The hook intercepts the commit and triggers the quiz automatically.

### Without Hook (Manual)

Invoke the skill directly before committing:

```
> /understando
```

Then commit after passing.

### Quiz Flow

```
Select quiz difficulty:
1. Easy - Surface-level understanding
2. Medium - Moderate depth, some context required
3. Hard - Deep understanding, edge cases, architectural implications

Enter choice (1/2/3) or press Enter for default:
```

Answer 5 questions about your changes. Score 80% or higher to pass!

### Difficulty Levels

| Level | Tests | Example Question |
|-------|-------|------------------|
| **Easy** | Basic comprehension | "What function was modified?" |
| **Medium** | Intent and context | "Why was this validation added?" |
| **Hard** | Edge cases, architecture | "What edge case could break this?" |

### Skipping

Type `skip` when prompted to bypass the quiz. You'll see a gentle reminder about the importance of understanding your code.

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  User: "commit these changes"                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Hook detects "git commit" → blocks → tells Claude to quiz  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Claude runs /understando skill                             │
│  - Reads staged diff                                        │
│  - Asks difficulty level                                    │
│  - Generates 5 questions                                    │
│  - Judges answers (MCQ: exact, free-text: LLM)              │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────┐        ┌──────────────────────┐
│  ≥80%: PASS          │        │  <80%: FAIL          │
│  Commit proceeds     │        │  Show explanations   │
│  (--understando-     │        │  Retry or skip?      │
│   passed flag)       │        │                      │
└──────────────────────┘        └──────────────────────┘
```

## Requirements

- Claude Code
- `jq` (for JSON parsing in the hook)

## Compatibility

| Feature | Supported |
|---------|-----------|
| Claude Code | Yes |
| Other agents | Skill only (no hook support) |

## License

MIT
