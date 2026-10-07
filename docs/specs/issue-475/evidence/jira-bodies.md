---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Rendered Jira bodies (T10, issue-475)

What the-loop sends to Jira for the four bodies that matter most, as **ADF** (Jira Cloud, REST v3) and **wiki markup** (Jira Data Center, REST v2). They are the golden files under [`cli/tests/fixtures/jira/`](../../../../cli/tests/fixtures/jira/), which `cli/tests/test_jira_format.py` renders from the real code on every run (T2) — so this record and the code cannot drift without a test failing. Regenerate both with `THE_LOOP_REGEN_JIRA_GOLDEN=1` and review the diff by eye.

Every comment the-loop writes ends with the visible self-marker line `🤖 the-loop, autonomous comment · [the-loop:agent-comment]` (R4.6). On wiki markup its brackets are escaped, so Jira never reads the sentinel as a link.

## The phase-selection checklist

`selection._checklist_body` for the shipped outer loop with every setting offered, marked for Jira. Every `- [ ]` / `- [x]` row is an ADF `taskItem` (`TODO` / `DONE`); on wiki markup a row is `* (/)` (ticked) or `* (x)` (not). `<details>` blocks are dropped with each summary kept bold, and the `<!-- the-loop:phase-selection -->` marker is the visible `[the-loop:phase-selection]` the gate restores on read.

### The phase-selection checklist — ADF

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "heading",
      "attrs": {
        "level": 2
      },
      "content": [
        {
          "type": "text",
          "text": "🤖 the-loop — which phases does this work item need?"
        }
      ]
    },
    {
      "type": "blockquote",
      "content": [
        {
          "type": "paragraph",
          "content": [
            {
              "type": "text",
              "text": "⚡ Quick start:",
              "marks": [
                {
                  "type": "strong"
                }
              ]
            },
            {
              "type": "text",
              "text": " reply "
            },
            {
              "type": "text",
              "text": "the-loop execute",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": " with the boxes untouched to run the full process — every phase that is already ticked, and none of the optional ones."
            }
          ]
        },
        {
          "type": "paragraph",
          "content": [
            {
              "type": "text",
              "text": "✏️ To tailor it:",
              "marks": [
                {
                  "type": "strong"
                }
              ]
            },
            {
              "type": "text",
              "text": " untick anything this work item does not need, tick anything optional it does want, then reply "
            },
            {
              "type": "text",
              "text": "the-loop execute",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": "."
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ How this works",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Nothing runs until an authorized user replies "
        },
        {
          "type": "text",
          "text": "the-loop execute",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": ". The tick state at that moment is frozen and becomes the graph this item walks."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "A doc fix usually needs little more than implementation and verification; a feature usually needs every phase."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "You can also put the list in the reply itself — a checklist in the "
        },
        {
          "type": "text",
          "text": "the-loop execute",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " comment wins over the boxes here. Either way the "
        },
        {
          "type": "text",
          "text": "authorization is your reply",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": ": the tick state is a proposal, and saying the keyword is what makes it yours."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Only the boxes under "
        },
        {
          "type": "text",
          "text": "Phases",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " change what work is done. Everything under "
        },
        {
          "type": "text",
          "text": "Settings",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " is about how and where it is done, and each has a default."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 3
      },
      "content": [
        {
          "type": "text",
          "text": "🧩 Phases — ticked ones run"
        }
      ]
    },
    {
      "type": "taskList",
      "attrs": {
        "localId": "the-loop-tasks-1"
      },
      "content": [
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-1",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "brainstorming"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-2",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "requirements-definition"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-3",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "requirements-approval"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-4",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "design"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-5",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "test-planning"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-6",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "design-approval"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-7",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "tasks-breakdown"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-8",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "implementation"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-9",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "verification"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-10",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "self-review"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-11",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "critic-review"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-12",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "security-review"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-13",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "evidence"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-14",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "capability-docs"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-15",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "reviewer-briefing"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-16",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "human-approval"
            }
          ]
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 4
      },
      "content": [
        {
          "type": "text",
          "text": "➕ Optional phases — off unless you tick them"
        }
      ]
    },
    {
      "type": "taskList",
      "attrs": {
        "localId": "the-loop-tasks-2"
      },
      "content": [
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-17",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "design-critic-review — a different model/harness reviews the completed design.md against the requirements, before the testing plan and the task DAG are derived from it (the design is locked later, at design-approval — issue-281)"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "⚠️ "
        },
        {
          "type": "text",
          "text": "Every phase of this loop is selectable — including the reviews, the security review and the approval gate.",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " Nothing but this question is mandatory."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ How a skipped phase is recorded",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "The phases this item skips are recorded as its own declared choice — in its work-item state, in a confirmation comment here, and in every "
        },
        {
          "type": "text",
          "text": "the-loop check",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " from now on — so a lighter run is always a visible one."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 3
      },
      "content": [
        {
          "type": "text",
          "text": "⚙️ Settings — not phases; each has a default"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "These decide how and where the work happens, not what work is done. Leave alone any you do not care about."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 4
      },
      "content": [
        {
          "type": "text",
          "text": "📍 Where should the outer loop happen?"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Default:",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " on "
        },
        {
          "type": "text",
          "text": "this work item",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": ", here. Tick the box to move it to a pull request."
        }
      ]
    },
    {
      "type": "taskList",
      "attrs": {
        "localId": "the-loop-tasks-3"
      },
      "content": [
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-18",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "outer-loop-on-pull-request",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": " — on a pull request in this repository."
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ What this means",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Not a phase — it is where the requirements, design, testing plan and task list are iterated with you. Leave it unticked (the default) and they happen "
        },
        {
          "type": "text",
          "text": "on this work item",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": ", here. Tick it and they happen on a pull request instead."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Either way the artifacts are committed files linked from here, and each repository this work item contributes code to gets its own pull request for the inner loop."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 4
      },
      "content": [
        {
          "type": "text",
          "text": "📄 Publish the spec chain as a Claude artifact too?"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Default:",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " no — the markdown files only. Only the "
        },
        {
          "type": "text",
          "text": "claude",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " harness can publish one."
        }
      ]
    },
    {
      "type": "taskList",
      "attrs": {
        "localId": "the-loop-tasks-4"
      },
      "content": [
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-19",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "claude-artifact",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": " — one Claude artifact for this work item ("
            },
            {
              "type": "text",
              "text": "claude",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": " harness only)."
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ What this means",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Not a phase, and off unless you tick it. The requirements, design, testing plan and task list become one page with a tab per file, which you can read and comment on in Claude."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "On any other harness the-loop ignores this box. The markdown files stay the source of truth either way, and every gate still reads them."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 4
      },
      "content": [
        {
          "type": "text",
          "text": "🧵 How many sessions should this work item's pull requests get?"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Default:",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " "
        },
        {
          "type": "text",
          "text": "cross-repository",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": ", already ticked. "
        },
        {
          "type": "text",
          "text": "Tick exactly one",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " to change it."
        }
      ]
    },
    {
      "type": "taskList",
      "attrs": {
        "localId": "the-loop-tasks-5"
      },
      "content": [
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-20",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "pr-sessions-never",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": " — every pull request's events land in "
            },
            {
              "type": "text",
              "text": "this",
              "marks": [
                {
                  "type": "strong"
                }
              ]
            },
            {
              "type": "text",
              "text": " work item's one session."
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-21",
            "state": "DONE"
          },
          "content": [
            {
              "type": "text",
              "text": "pr-sessions-cross-repository",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": " — only a pull request in "
            },
            {
              "type": "text",
              "text": "another",
              "marks": [
                {
                  "type": "strong"
                }
              ]
            },
            {
              "type": "text",
              "text": " repository gets its own session; one in this repository is this work item's own delivery."
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-22",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "pr-sessions-always",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": " — "
            },
            {
              "type": "text",
              "text": "every",
              "marks": [
                {
                  "type": "strong"
                }
              ]
            },
            {
              "type": "text",
              "text": " pull request delivering this work item gets its own session, this repository's included."
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ What this means",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Not a phase — it is how many harness conversations run for this item."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Leave them alone and "
        },
        {
          "type": "text",
          "text": "cross-repository",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " stands — the operator's "
        },
        {
          "type": "text",
          "text": "routing.tmux.sessionPerPr",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": ". Ticking none, or more than one, means the same thing."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "A pull request only ever gets a session when it can get a "
        },
        {
          "type": "text",
          "text": "working tree of its own",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": ", in every mode: where it cannot, the event is delivered into this work item's session and recorded as "
        },
        {
          "type": "text",
          "text": "session.pr_session_declined",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": "."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 4
      },
      "content": [
        {
          "type": "text",
          "text": "💬 Is this work item worked in a channel of its own?"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Default:",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " none declared — this item's updates go to the operator's central channel."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Reply "
        },
        {
          "type": "text",
          "text": "the-loop add-channel slack@C0123ABCD",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " (its conversation id, not "
        },
        {
          "type": "text",
          "text": "#name",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": ") to give it a room of its own."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ What this means",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Not a phase — it is where the-loop posts this item's updates, and where messages from authorized users reach it."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Declare it in a comment of its own, before or after this gate — the order does not matter, and a comment may carry only one keyword."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 4
      },
      "content": [
        {
          "type": "text",
          "text": "🛠️ Which harness should this work item run on?"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Default:",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " "
        },
        {
          "type": "text",
          "text": "claude",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": ", this deployment's default. "
        },
        {
          "type": "text",
          "text": "Tick at most one",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " to change it."
        }
      ]
    },
    {
      "type": "taskList",
      "attrs": {
        "localId": "the-loop-tasks-6"
      },
      "content": [
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-23",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "harness-claude",
              "marks": [
                {
                  "type": "code"
                }
              ]
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-24",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "harness-codex",
              "marks": [
                {
                  "type": "code"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ What this means",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Not a phase — it is the agent CLI its session is. A model or effort ticked below is kept only if the harness it ends up on can run it."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Leave them alone and the default stands. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 4
      },
      "content": [
        {
          "type": "text",
          "text": "🧠 Which model should this work item run on?"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Default:",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " "
        },
        {
          "type": "text",
          "text": "sonnet",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": ", the "
        },
        {
          "type": "text",
          "text": "claude",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " harness's default model. "
        },
        {
          "type": "text",
          "text": "Tick at most one",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " to change it."
        }
      ]
    },
    {
      "type": "taskList",
      "attrs": {
        "localId": "the-loop-tasks-7"
      },
      "content": [
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-25",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "model-opus",
              "marks": [
                {
                  "type": "code"
                }
              ]
            },
            {
              "type": "text",
              "text": " — deepest"
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-26",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "model-sonnet",
              "marks": [
                {
                  "type": "code"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ What this means",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Not a phase — it is what the session is."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Leave them alone and the default stands. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 4
      },
      "content": [
        {
          "type": "text",
          "text": "🎚️ How hard should it think?"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Default:",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " the harness's own default effort. "
        },
        {
          "type": "text",
          "text": "Tick at most one",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " to change it."
        }
      ]
    },
    {
      "type": "taskList",
      "attrs": {
        "localId": "the-loop-tasks-8"
      },
      "content": [
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-27",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "effort-low",
              "marks": [
                {
                  "type": "code"
                }
              ]
            }
          ]
        },
        {
          "type": "taskItem",
          "attrs": {
            "localId": "the-loop-task-28",
            "state": "TODO"
          },
          "content": [
            {
              "type": "text",
              "text": "effort-high",
              "marks": [
                {
                  "type": "code"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "ℹ️ What this means",
          "marks": [
            {
              "type": "strong"
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Not a phase, and independent of the model above."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Leave them alone and the default stands. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 3
      },
      "content": [
        {
          "type": "text",
          "text": "✅ Ready?"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Reply "
        },
        {
          "type": "text",
          "text": "the-loop execute",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": ". The boxes as they stand at that moment are frozen as this work item's selection."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "[the-loop:phase-selection]"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "🤖 the-loop, autonomous comment · [the-loop:agent-comment]"
        }
      ]
    }
  ]
}
```

### The phase-selection checklist — wiki markup

```text
h2. 🤖 the-loop — which phases does this work item need?

{quote}
*⚡ Quick start:* reply {{the-loop execute}} with the boxes untouched to run the full process — every phase that is already ticked, and none of the optional ones.

*✏️ To tailor it:* untick anything this work item does not need, tick anything optional it does want, then reply {{the-loop execute}}.
{quote}

*ℹ️ How this works*

Nothing runs until an authorized user replies {{the-loop execute}}. The tick state at that moment is frozen and becomes the graph this item walks.

A doc fix usually needs little more than implementation and verification; a feature usually needs every phase.

You can also put the list in the reply itself — a checklist in the {{the-loop execute}} comment wins over the boxes here. Either way the *authorization is your reply*: the tick state is a proposal, and saying the keyword is what makes it yours.

Only the boxes under *Phases* change what work is done. Everything under *Settings* is about how and where it is done, and each has a default.

h3. 🧩 Phases — ticked ones run

* (/) brainstorming
* (/) requirements-definition
* (/) requirements-approval
* (/) design
* (/) test-planning
* (/) design-approval
* (/) tasks-breakdown
* (/) implementation
* (/) verification
* (/) self-review
* (/) critic-review
* (/) security-review
* (/) evidence
* (/) capability-docs
* (/) reviewer-briefing
* (/) human-approval

h4. ➕ Optional phases — off unless you tick them

* (x) design-critic-review — a different model/harness reviews the completed design.md against the requirements, before the testing plan and the task DAG are derived from it (the design is locked later, at design-approval — issue-281)

⚠️ *Every phase of this loop is selectable — including the reviews, the security review and the approval gate.* Nothing but this question is mandatory.

*ℹ️ How a skipped phase is recorded*

The phases this item skips are recorded as its own declared choice — in its work-item state, in a confirmation comment here, and in every {{the-loop check}} from now on — so a lighter run is always a visible one.

h3. ⚙️ Settings — not phases; each has a default

These decide how and where the work happens, not what work is done. Leave alone any you do not care about.

h4. 📍 Where should the outer loop happen?

*Default:* on *this work item*, here. Tick the box to move it to a pull request.

* (x) {{outer-loop-on-pull-request}} — on a pull request in this repository.

*ℹ️ What this means*

Not a phase — it is where the requirements, design, testing plan and task list are iterated with you. Leave it unticked (the default) and they happen *on this work item*, here. Tick it and they happen on a pull request instead.

Either way the artifacts are committed files linked from here, and each repository this work item contributes code to gets its own pull request for the inner loop.

h4. 📄 Publish the spec chain as a Claude artifact too?

*Default:* no — the markdown files only. Only the {{claude}} harness can publish one.

* (x) {{claude-artifact}} — one Claude artifact for this work item ({{claude}} harness only).

*ℹ️ What this means*

Not a phase, and off unless you tick it. The requirements, design, testing plan and task list become one page with a tab per file, which you can read and comment on in Claude.

On any other harness the-loop ignores this box. The markdown files stay the source of truth either way, and every gate still reads them.

h4. 🧵 How many sessions should this work item's pull requests get?

*Default:* {{cross-repository}}, already ticked. *Tick exactly one* to change it.

* (x) {{pr-sessions-never}} — every pull request's events land in *this* work item's one session.
* (/) {{pr-sessions-cross-repository}} — only a pull request in *another* repository gets its own session; one in this repository is this work item's own delivery.
* (x) {{pr-sessions-always}} — *every* pull request delivering this work item gets its own session, this repository's included.

*ℹ️ What this means*

Not a phase — it is how many harness conversations run for this item.

Leave them alone and {{cross-repository}} stands — the operator's {{routing.tmux.sessionPerPr}}. Ticking none, or more than one, means the same thing.

A pull request only ever gets a session when it can get a *working tree of its own*, in every mode: where it cannot, the event is delivered into this work item's session and recorded as {{session.pr_session_declined}}.

h4. 💬 Is this work item worked in a channel of its own?

*Default:* none declared — this item's updates go to the operator's central channel.

Reply {{the-loop add-channel slack@C0123ABCD}} (its conversation id, not {{#name}}) to give it a room of its own.

*ℹ️ What this means*

Not a phase — it is where the-loop posts this item's updates, and where messages from authorized users reach it.

Declare it in a comment of its own, before or after this gate — the order does not matter, and a comment may carry only one keyword.

h4. 🛠️ Which harness should this work item run on?

*Default:* {{claude}}, this deployment's default. *Tick at most one* to change it.

* (x) {{harness-claude}}
* (x) {{harness-codex}}

*ℹ️ What this means*

Not a phase — it is the agent CLI its session is. A model or effort ticked below is kept only if the harness it ends up on can run it.

Leave them alone and the default stands. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for.

h4. 🧠 Which model should this work item run on?

*Default:* {{sonnet}}, the {{claude}} harness's default model. *Tick at most one* to change it.

* (x) {{model-opus}} — deepest
* (x) {{model-sonnet}}

*ℹ️ What this means*

Not a phase — it is what the session is.

Leave them alone and the default stands. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for.

h4. 🎚️ How hard should it think?

*Default:* the harness's own default effort. *Tick at most one* to change it.

* (x) {{effort-low}}
* (x) {{effort-high}}

*ℹ️ What this means*

Not a phase, and independent of the model above.

Leave them alone and the default stands. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for.

h3. ✅ Ready?

Reply {{the-loop execute}}. The boxes as they stand at that moment are frozen as this work item's selection.

\[the-loop:phase-selection\]

🤖 the-loop, autonomous comment · \[the-loop:agent-comment\]
```

## A gate's request-review

The `request-review` hook's body for `design-approval` on `jira-proj-7`, marked for Jira.

### A gate's request-review — ADF

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "🤖 "
        },
        {
          "type": "text",
          "text": "the-loop",
          "marks": [
            {
              "type": "em"
            }
          ]
        },
        {
          "type": "text",
          "text": " — "
        },
        {
          "type": "text",
          "text": "design-approval",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " is ready for review."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Work item "
        },
        {
          "type": "text",
          "text": "jira-proj-7",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " has reached a human gate. Reply with an approval, an approval with comments, or the changes you want."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "🤖 the-loop, autonomous comment · [the-loop:agent-comment]"
        }
      ]
    }
  ]
}
```

### A gate's request-review — wiki markup

```text
🤖 _the-loop_ — *design-approval* is ready for review.

Work item {{jira-proj-7}} has reached a human gate. Reply with an approval, an approval with comments, or the changes you want.

🤖 the-loop, autonomous comment · \[the-loop:agent-comment\]
```

## An ask

`ask_body` for a `session.awaiting_input` event (the question, numbered options and inline code), marked for Jira. The envelope (`<!-- the-loop:event {…} -->`) is dropped: Jira has no hidden text.

### An ask — ADF

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Question:",
          "marks": [
            {
              "type": "strong"
            }
          ]
        },
        {
          "type": "text",
          "text": " which database should the migration target?"
        }
      ]
    },
    {
      "type": "orderedList",
      "attrs": {
        "order": 1
      },
      "content": [
        {
          "type": "listItem",
          "content": [
            {
              "type": "paragraph",
              "content": [
                {
                  "type": "text",
                  "text": "Postgres 16 — what production runs today"
                }
              ]
            }
          ]
        },
        {
          "type": "listItem",
          "content": [
            {
              "type": "paragraph",
              "content": [
                {
                  "type": "text",
                  "text": "MySQL 8 — what the reporting replica runs"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Reply on this ticket; the default is "
        },
        {
          "type": "text",
          "text": "postgres",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " if nobody answers."
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "🤖 the-loop, autonomous comment · [the-loop:agent-comment]"
        }
      ]
    }
  ]
}
```

### An ask — wiki markup

```text
*Question:* which database should the migration target?

# Postgres 16 — what production runs today
# MySQL 8 — what the reporting replica runs

Reply on this ticket; the default is {{postgres}} if nobody answers.

🤖 the-loop, autonomous comment · \[the-loop:agent-comment\]
```

## The PR-briefing template

`skills/the-loop/templates/pr-briefing.md` as written. Its HTML comments are dropped; the `<PR title>`-style placeholders are kept as text; the `mermaid` block keeps its language in ADF and is a plain `{code}` on wiki, whose macro has no mermaid formatter.

### The PR-briefing template — ADF

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "heading",
      "attrs": {
        "level": 1
      },
      "content": [
        {
          "type": "text",
          "text": "<PR title> — reviewer briefing"
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 2
      },
      "content": [
        {
          "type": "text",
          "text": "TL;DR"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "One or two sentences: what this PR does and why."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 2
      },
      "content": [
        {
          "type": "text",
          "text": "Where to focus (in this order)"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Prioritized so a reviewer of AI-authored work knows what to scrutinize first."
        }
      ]
    },
    {
      "type": "orderedList",
      "attrs": {
        "order": 1
      },
      "content": [
        {
          "type": "listItem",
          "content": [
            {
              "type": "paragraph",
              "content": [
                {
                  "type": "text",
                  "text": "<highest-priority area>",
                  "marks": [
                    {
                      "type": "strong"
                    }
                  ]
                },
                {
                  "type": "text",
                  "text": " — "
                },
                {
                  "type": "text",
                  "text": "<path>",
                  "marks": [
                    {
                      "type": "code"
                    }
                  ]
                },
                {
                  "type": "text",
                  "text": " — why it matters / what to check."
                }
              ]
            }
          ]
        },
        {
          "type": "listItem",
          "content": [
            {
              "type": "paragraph",
              "content": [
                {
                  "type": "text",
                  "text": "<next>",
                  "marks": [
                    {
                      "type": "strong"
                    }
                  ]
                },
                {
                  "type": "text",
                  "text": " — "
                },
                {
                  "type": "text",
                  "text": "<path>",
                  "marks": [
                    {
                      "type": "code"
                    }
                  ]
                },
                {
                  "type": "text",
                  "text": " — …"
                }
              ]
            }
          ]
        },
        {
          "type": "listItem",
          "content": [
            {
              "type": "paragraph",
              "content": [
                {
                  "type": "text",
                  "text": "<lower-risk / skim>",
                  "marks": [
                    {
                      "type": "strong"
                    }
                  ]
                },
                {
                  "type": "text",
                  "text": " — …"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 2
      },
      "content": [
        {
          "type": "text",
          "text": "What changed (map)"
        }
      ]
    },
    {
      "type": "codeBlock",
      "attrs": {
        "language": "mermaid"
      },
      "content": [
        {
          "type": "text",
          "text": "%% A diagram of the change — components touched, or commit-by-commit evolution.\nflowchart TD\n  A[area] --> B[area]"
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 2
      },
      "content": [
        {
          "type": "text",
          "text": "Key decisions & why (education)"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "The low-level calls the harness made, so the reviewer learns the design, not just the diff."
        }
      ]
    },
    {
      "type": "bulletList",
      "content": [
        {
          "type": "listItem",
          "content": [
            {
              "type": "paragraph",
              "content": [
                {
                  "type": "text",
                  "text": "<decision>",
                  "marks": [
                    {
                      "type": "strong"
                    }
                  ]
                },
                {
                  "type": "text",
                  "text": " — why; trade-off; link to "
                },
                {
                  "type": "text",
                  "text": "docs/decisions/decision-<nnn>.md",
                  "marks": [
                    {
                      "type": "code"
                    }
                  ]
                },
                {
                  "type": "text",
                  "text": "."
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 2
      },
      "content": [
        {
          "type": "text",
          "text": "Evidence"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Tests / checks / screenshots proving the acceptance criteria are met (e.g. CI green,"
        },
        {
          "type": "hardBreak"
        },
        {
          "type": "text",
          "text": "pre-commit",
          "marks": [
            {
              "type": "code"
            }
          ]
        },
        {
          "type": "text",
          "text": " output, live smoke test)."
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {
        "level": 2
      },
      "content": [
        {
          "type": "text",
          "text": "Open questions for the reviewer"
        }
      ]
    },
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "Anything the reviewer must decide or is explicitly being asked to confirm."
        }
      ]
    }
  ]
}
```

### The PR-briefing template — wiki markup

```text
h1. <PR title> — reviewer briefing

h2. TL;DR

One or two sentences: what this PR does and why.

h2. Where to focus (in this order)

Prioritized so a reviewer of AI-authored work knows what to scrutinize first.

# *<highest-priority area>* — {{<path>}} — why it matters / what to check.
# *<next>* — {{<path>}} — …
# *<lower-risk / skim>* — …

h2. What changed (map)

{code}
%% A diagram of the change — components touched, or commit-by-commit evolution.
flowchart TD
  A[area] --> B[area]
{code}

h2. Key decisions & why (education)

The low-level calls the harness made, so the reviewer learns the design, not just the diff.

* *<decision>* — why; trade-off; link to {{docs/decisions/decision-<nnn>.md}}.

h2. Evidence

Tests / checks / screenshots proving the acceptance criteria are met (e.g. CI green,
{{pre-commit}} output, live smoke test).

h2. Open questions for the reviewer

Anything the reviewer must decide or is explicitly being asked to confirm.
```
