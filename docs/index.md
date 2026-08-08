---
layout: home

hero:
  name: the-loop
  text: The loop for everything!
  tagline: >-
    An opinionated product-development lifecycle, shipped as an executable process graph
    and a daemon that runs it. Nodes are the steps, hooks are the checks at their
    boundaries, edges route on outcomes — so the process is a declaration, not a habit.
  actions:
    - theme: brand
      text: What is the-loop?
      link: /guide/what-is-the-loop
    - theme: alt
      text: Quickstart
      link: /guide/quickstart
    - theme: alt
      text: the-loop CLI
      link: /cli/
    - theme: alt
      text: View on GitHub
      link: https://github.com/MadaraUchiha-314/the-loop

features:
  - title: Two loops, one process
    details: >-
      An outer loop per work item (brainstorm → requirements → design → testing plan →
      tasks → implementation → verification → review → complete) and an inner loop per
      pull request, each in its own session. They meet at one seam: the work item waits
      until every pull request delivering it has finished.
    link: /capabilities/process-graph
    linkText: How the graph works
  - title: The process is executable
    details: >-
      Both loops ship as data inside the CLI. A gate reads checked-in artifacts, never
      prose; a claim carries no verdict; a forced transition moves the pointer and never
      forges a result. The graph assigns work as well as judging it.
  - title: A CLI that drives it
    details: >-
      A lightweight, extensible Python CLI (the-loop) turning ticket and pull-request
      activity into agent runs: webhook and poll ingress, one record per work item with a
      session per pull request, execution control, and a structured event log.
    link: /cli/
    linkText: Explore the CLI
  - title: Gated, reviewed, documented
    details: >-
      Every phase is gated by human review, and testing is planned before it is executed.
      Every decision leaves a paper trail. Capability docs and the user-facing docs are
      updated in the same pull request as the change that made them wrong.
---
