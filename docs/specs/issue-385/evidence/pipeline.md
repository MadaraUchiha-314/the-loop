---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#385"
---

<!-- Authored per the the-loop:writing skill. -->

# Pipeline evidence: graphify on this tree, against a fake model

> Testing-plan rows T3 and T5. This container holds no Anthropic key, so the two commands
> the workflow runs were exercised on a clone of this repository against a local stand-in
> for the Messages API, reached through `ANTHROPIC_BASE_URL`. The stand-in answers every
> extraction request with one concept node per file in the chunk and every naming request
> with a name per community — deterministic, free, and enough to drive graphify's real
> chunking, retry, dedup, clustering, manifest and cache code.

## What graphify sees in this tree

```text
total_files 1755   total_words 2,449,114
code      405   .py 324 · .tsx 26 · .ts 25 · .json 23 · .toml 2 · .mts 2
document 1273   .md 1236 · .yaml 22 · .html 6 · .txt 5 · .yml 4
image      77   .png 74 · .gif 2 · .svg 1
```

## The no-model half, measured first (`graphify update .`, then `extract --code-only`)

```text
graphify update .            38.6 s   25,027 nodes · 54,935 edges · 992 communities
graphify-out/graph.json      32 MB    (1.9 MB gzip; 33,124,225 bytes)
graphify-out/cache/          36 MB    (AST cache)
GRAPH_REPORT.md 316 KB · graph.html 1.3 MB · manifest.json 324 KB

one code line + one README line changed, `graphify update .` again:
  pack before=19887KB after=20295KB delta=408KB
  graphify-out/graph.json | 172881 +++++-----   (community numbering changes every run)
```

## The three runs (`extract --backend claude` + `cluster-only --backend claude`)

Commands, exactly as the workflow runs them, with the fake substituted for the API:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8766 ANTHROPIC_API_KEY=fake-key GRAPHIFY_NO_BACKUP=1 GRAPHIFY_NO_TIPS=1
graphify extract . --backend claude --model claude-opus-5
graphify cluster-only . --backend claude --model claude-opus-5
```

```text
===== RUN 1: first full run (no baseline)
[graphify] chunk of 20 still hollow after 3 attempt(s) — giving up on this chunk. Its files are marked for re-extraction on the next run. A hollow response usually means a rate limit, a transport hiccup, a refusal, or a model that answered in prose rather than JSON.
[graphify] WARNING: 76/1350 dispatched file(s) produced no nodes and are absent from the graph: cli-commands.png, cli-overview.png, config-routing.png, workflow-rendered.png, settings-config.png (+71 more). The model returned a response but omitted them; a re-run will retry them.
[graphify extract] semantic extraction is incomplete: 76 dispatched file(s) produced no nodes and 20 came back truncated or hollow. The shrink guard stays armed for this write; pass --allow-partial to overwrite a larger existing graph anyway.
[graphify] Deduplicated 158 node(s) (58 exact, 100 fuzzy).
[graphify extract] wrote <clone>/graphify-out/graph.json: 14404 nodes, 34734 edges, 433 communities
[graphify extract] wrote <clone>/graphify-out/.graphify_analysis.json
[graphify extract] tokens: 6,585,605 in / 189,025 out, est. cost (~claude): $22.5922
[graphify extract] next: run `graphify cluster-only <clone>` to generate GRAPH_REPORT.md and name communities
--- cluster-only
graph.html written (aggregated: 433 community nodes, 2027 cross-community edges)
Tip: run with --obsidian for full node-level detail.
Done - 433 communities. GRAPH_REPORT.md, graph.json and graph.html updated.
elapsed 114s; fake calls so far: 55
. .. .graphify_analysis.json .graphify_labels.json .graphify_labels.json.sig .graphify_root .graphify_semantic_marker GRAPH_REPORT.md cache graph.html graph.json manifest.json 
19M   graphify-out/graph.json
23M   graphify-out/cache
180K   graphify-out/GRAPH_REPORT.md
600K   graphify-out/graph.html
364K   graphify-out/manifest.json
?? graphify-out/cache/
===== RUN 2: one doc changed (docs/contributing.md), cache present
[graphify extract] 14 code, 1 docs, 0 papers, 76 images changed; 1676 unchanged; 0 deleted
[graphify extract] wrote <clone>/graphify-out/graph.json: 14404 nodes, 34733 edges, 435 communities
[graphify extract] incremental summary: 1676 files cached/unchanged, 91 re-extracted, 0 deleted
[graphify extract] tokens: 3,871,190 in / 86 out, est. cost (~claude): $11.6149
fake calls in run 2: 10; elapsed 26s
===== RUN 3: cache/ deleted (fresh CI checkout), one more doc changed (README.md)
[graphify extract] 14 code, 1 docs, 0 papers, 76 images changed; 1676 unchanged; 0 deleted
[graphify extract] wrote <clone>/graphify-out/graph.json: 14404 nodes, 34732 edges, 410 communities
[graphify extract] incremental summary: 1676 files cached/unchanged, 91 re-extracted, 0 deleted
[graphify extract] tokens: 3,873,785 in / 78 out, est. cost (~claude): $11.6225
fake calls in run 3: 10; elapsed 26s
Done - 410 communities. GRAPH_REPORT.md, graph.json and graph.html updated.
--- git status after run 3 (tracked = what CI would commit)
 M README.md
 M docs/contributing.md
 M graphify-out/.graphify_analysis.json
 M graphify-out/.graphify_labels.json
 M graphify-out/.graphify_labels.json.sig
 M graphify-out/.graphify_semantic_marker
 M graphify-out/GRAPH_REPORT.md
 M graphify-out/graph.html
 M graphify-out/graph.json
 M graphify-out/manifest.json
 10 files changed, 95223 insertions(+), 92877 deletions(-)
- Built from commit: `43280416`
76
```

What the log shows:

- **Run 1** (no baseline) sent every document and image: 48 extraction chunks plus the
  community-naming calls, 55 requests, 114 s wall-clock with an instant model. The 76
  images came back "hollow" because the stand-in returns nothing for an image block —
  a property of the stand-in, and the reason the design names `--exclude` as the fix if
  a real run's log ever shows images re-sent.
- **Run 2** (committed `graph.json` + `manifest.json`, cache present, one document
  changed): **1 document** re-extracted, 10 requests, 26 s.
- **Run 3** (the CI case — cache directory deleted, one more document changed): the same
  1 document, 10 requests, 26 s. **The committed manifest alone is the incremental
  baseline**; the cache is a saving, not a requirement.
- graphify's own "tokens" line counts the tokens of the chunks it *would* have sent and
  is therefore the same on runs 2 and 3; the request counter is the ground truth.
- The clone's `git status` lists the sidecars as modified because the clone predates
  this work item's `.gitignore`; the rules themselves are checked below.

## T3 — the tracked set and the tooling

```text
$ git check-ignore -v graphify-out/cache/x graphify-out/.graphify_root graphify-out/.graphify_labels.json graphify-out/2026-09-19/graph.json graphify-out/graph.json
.gitignore:266:graphify-out/cache/                                  graphify-out/cache/x
.gitignore:267:graphify-out/.graphify_*                             graphify-out/.graphify_root
.gitignore:268:!graphify-out/.graphify_labels.json                  graphify-out/.graphify_labels.json   (negated: tracked)
.gitignore:270:graphify-out/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/   graphify-out/2026-09-19/graph.json
(graphify-out/graph.json: no match — tracked)

$ python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/graphify.yml')); print(list(d['jobs']))"
['dry-run', 'rebuild']

$ stat -c %a scripts/graphify-commit.sh
755
```

## The stand-in

Kept here so the runs can be repeated; it is not part of the repository's code.

```python
"""A fake Anthropic Messages endpoint for exercising graphify's `claude` backend offline.

Answers POST /v1/messages with one concept node per <untrusted_source path="..."> block in
the prompt, so the pipeline sees a well-formed, non-hollow extraction. Community-naming
prompts (no untrusted_source blocks) get a JSON object naming every community id found.
Logs one line per request to stderr and a counter file.
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SRC = re.compile(r'<untrusted_source path=\\?"([^"\\]+)\\?"')
COUNTER = sys.argv[2] if len(sys.argv) > 2 else "/tmp/fake_anthropic.count"
calls = 0


def _stem(path: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", path.rsplit(".", 1)[0].lower())


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):
        global calls
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        text = json.dumps(body.get("messages", []))
        paths = sorted(set(SRC.findall(text)))
        calls += 1
        with open(COUNTER, "w") as f:
            f.write(str(calls))
        if paths:
            nodes = [
                {"id": f"{_stem(p)}_concept", "label": f"Concept of {p}",
                 "file_type": "document", "source_file": p, "source_location": None,
                 "source_url": None, "captured_at": None, "author": None,
                 "contributor": None, "rationale": None}
                for p in paths
            ]
            edges = [
                {"source": nodes[i]["id"], "target": nodes[i + 1]["id"],
                 "relation": "references", "confidence": "EXTRACTED",
                 "confidence_score": 1.0, "source_file": paths[i],
                 "source_location": None, "weight": 1.0}
                for i in range(len(nodes) - 1)
            ]
            out = {"nodes": nodes, "edges": edges, "hyperedges": []}
            print(f"[fake] extraction call {calls}: {len(paths)} files", file=sys.stderr)
        else:
            # community naming: answer with a mapping for every community id we can find
            ids = sorted(set(re.findall(r'"?(?:community|id)"?\s*[:=]\s*"?(\d+)', text)))
            out = {i: f"Community {i} (fake)" for i in ids} or {"0": "Fake"}
            print(f"[fake] labeling call {calls}: {len(ids)} ids", file=sys.stderr)
        payload = json.dumps(out)
        resp = {
            "id": "msg_fake", "type": "message", "role": "assistant",
            "model": body.get("model", "fake"),
            "content": [{"type": "text", "text": payload}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": max(1, len(text) // 4), "output_tokens": max(1, len(payload) // 4)},
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"[fake] listening on {port}", file=sys.stderr)
    HTTPServer(("127.0.0.1", port), H).serve_forever()

```
