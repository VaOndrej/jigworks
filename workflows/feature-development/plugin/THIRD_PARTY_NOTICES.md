# Third-party notices

Some skills in this plugin are adapted from MIT-licensed skill collections. They were rewritten
for headless agents inside the feature-development workflow (no interactive questions except
through the workflow's reply formats, no sub-agents, no tools or skills outside this package),
so none of them is a verbatim copy. The original copyright and permission notices follow.

## Which skill comes from where

| Skill in this plugin | Adapted from |
|----------------------|--------------|
| `brainstorm-before-planning` (strengthened) | Matt Pocock Skills: `productivity/grilling`; Superpowers: `brainstorming` |
| `clarify-before-planning` (strengthened) | Matt Pocock Skills: `productivity/grilling` |
| `slice-the-plan` | Matt Pocock Skills: `engineering/to-tickets`, `engineering/wayfinder` |
| `deep-modules` | Matt Pocock Skills: `engineering/codebase-design` |
| `tests-from-the-spec` (strengthened) | Matt Pocock Skills: `engineering/tdd`; Superpowers: `test-driven-development` |
| `test-first` | Matt Pocock Skills: `engineering/tdd`; Superpowers: `test-driven-development` |
| `verify-before-done` | Superpowers: `verification-before-completion` |
| `diagnose-before-fixing` | Matt Pocock Skills: `engineering/diagnosing-bugs`; Superpowers: `systematic-debugging` |
| `handle-review-findings` | Superpowers: `receiving-code-review` |
| `independent-review` (strengthened) | Matt Pocock Skills: `engineering/code-review` |
| `pr-summary` | Matt Pocock Skills: `engineering/pr` (Evidence and Merge Danger; see the note below) |

Sources:

- **Matt Pocock Skills**, version 1.3.1, by Matt Pocock, <https://github.com/mattpocock/skills>.
  MIT License.
- **Superpowers**, version 6.2.0, by Jesse Vincent, <https://github.com/obra/superpowers>.
  MIT License.

The upstream `engineering/pr` skill credits the idea of showing a change as a small tree or
call path to Dex Horthy's `show-me` skill (HumanLayer); `pr-summary` keeps only that one-line
idea, not its text.

## Matt Pocock Skills

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Superpowers

```
MIT License

Copyright (c) 2025 Jesse Vincent

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
