import json
import re
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE_PATH = HERE.parent / "assets" / "walkthrough-template.html"


def extract_main_script(html: str) -> str:
    scripts = re.findall(r"<script(?![^>]*walkthrough-data)[^>]*>(.*?)</script>", html, re.DOTALL)
    assert scripts, "Expected inline runtime <script> in template"
    return scripts[-1]


def valid_v3_payload():
    return {
        "schemaVersion": 3,
        "lang": "en",
        "meta": {
            "title": "Token Refresh Flow",
            "branch": "feat/token-refresh",
            "base": "main",
            "headSha": "a1b2c3d",
            "stats": {"files": 3, "added": 50, "removed": 10},
            "markdownPath": "/tmp/walkthrough.md",
        },
        "repo": {"root": "/Users/dev/project", "defaultEditor": "vscode"},
        "overview": {
            "title": "Deduplicated token refresh & session eviction",
            "summary": ["Updates token expiration handling across API clients."],
            "affects": "User authentication and session lifecycle",
            "split": {
                "recommendation": "Separate Dockerfile updates if deploying independently.",
                "boundaries": ["Token refresh lock", "Container build"],
            },
            "skim": ["README.md"],
        },
        "slices": [
            {
                "id": "token-refresh",
                "title": "Deduplicate concurrent token refresh",
                "summary": ["Coordinates parallel 401 responses behind a single refresh promise."],
                "files": [
                    {
                        "role": "Token Service",
                        "path": "src/auth/token.ts",
                        "startLine": 1,
                        "endLine": 80,
                        "status": "modified",
                        "summary": "Core token parsing and validation routines.",
                    }
                ],
                "headsUp": [
                    {
                        "title": "Parallel refresh race window",
                        "body": "Concurrent API calls can trigger parallel refresh requests before lock is acquired.",
                        "refs": [{"path": "src/auth/token.ts", "startLine": 42, "endLine": 50}],
                        "lookFor": "Check if an in-flight refresh promise is deduplicated.",
                    }
                ],
                "qa": ["Test token expiry with expired JWT."],
            },
            {
                "id": "session-eviction",
                "title": "Evict stale credentials on failure",
                "summary": ["Clears cached tokens when refresh fails with 401."],
                "files": [
                    {
                        "role": "Eviction Handler",
                        "path": "src/auth/token.ts",
                        "startLine": 90,
                        "endLine": 120,
                        "summary": "Clears storage and resets client state.",
                    }
                ],
                "headsUp": [],
                "qa": [],
            },
        ],
        "crossCutting": {
            "title": "Cross-Cutting Notes",
            "headsUp": [
                {
                    "title": "Session cleanup ordering",
                    "body": "Queued callers must reject cleanly when eviction runs.",
                    "refs": [],
                }
            ],
            "qa": ["Expire refresh token mid-flight."],
        },
    }


class TestWalkthroughTemplate(unittest.TestCase):
    def setUp(self):
        self.assertTrue(TEMPLATE_PATH.exists(), "Template file must exist")
        self.content = TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_template_size_is_lean(self):
        size_kb = len(self.content.encode("utf-8")) / 1024
        self.assertLess(
            size_kb,
            25,
            f"Template size is {size_kb:.1f} KB, expected < 25 KB without base64 bloat",
        )

    def test_no_embedded_base64_or_external_cdns(self):
        self.assertNotIn(";base64,d09GMgABAAAA", self.content)
        self.assertNotIn("data:font/woff2;base64", self.content)
        stripped = self.content.replace("http://www.w3.org/2000/svg", "")
        self.assertNotIn("https://", stripped)
        self.assertNotIn("http://", stripped)

    def test_local_vazirmatn_font_stack(self):
        self.assertIn('local("Vazirmatn")', self.content)
        self.assertIn('local("Vazir")', self.content)

    def test_one_light_and_one_dark_pro_tokens(self):
        for token in ("--bg:#fafafa", "--bg:#282c34", "--accent:#4078f2", "--accent:#61afef"):
            self.assertIn(token, self.content)

    def test_scrollable_layout_has_no_sticky_fixed_or_footer(self):
        css = re.search(r"<style>(.*?)</style>", self.content, re.DOTALL).group(1)
        self.assertNotRegex(css, r"position\s*:\s*(sticky|fixed)")
        self.assertNotIn("letter-spacing", css)
        self.assertNotIn("text-transform", css)
        self.assertIn("max-width:780px", css)
        self.assertNotIn("<footer", self.content)
        self.assertNotIn("h('footer'", self.content)
        self.assertNotIn(".card[hidden]", self.content)
        self.assertIn("shaHint", self.content)

    def test_editor_schemes_supported(self):
        for ed in ["vscode", "cursor", "windsurf", "zed", "android-studio", "goland", "idea", "copy"]:
            self.assertIn(ed, self.content)
        self.assertIn("Android Studio", self.content)
        self.assertIn("GoLand", self.content)

    def test_copy_button_and_clipboard_support(self):
        self.assertIn("clipboard.writeText", self.content)
        self.assertIn("cp-btn", self.content)

    def test_rtl_branch_arrow_direction(self):
        self.assertIn("R?'←':'→'", self.content)

    def test_rtl_rich_arrow_normalization(self):
        self.assertIn("replace(/[→➔➜]|->/g,'←')", self.content)

    def test_mount_fallback_helper(self):
        self.assertIn(
            "const mount=(el,...ch)=>{if(el.replaceChildren)el.replaceChildren(...ch);else{",
            self.content,
        )

    def test_runtime_script_syntax_and_schema_v3_check_in_node(self):
        script = extract_main_script(self.content)
        # Extract check(d) and helpers by running the script inside a minimal DOM stub in Node
        # that also captures `check` and `build` behavior.
        valid = valid_v3_payload()
        minimal = {
            "schemaVersion": 3,
            "lang": "en",
            "meta": {
                "title": "A" * 220,
                "branch": "fix/single",
                "base": "main",
                "headSha": "deadbee",
                "stats": {"files": 1, "added": 5, "removed": 2},
            },
            "overview": {
                "title": "Single slice overview",
                "affects": "Core parser",
            },
            "slices": [
                {
                    "id": "only-slice",
                    "title": "Only slice",
                    "summary": ["One line summary."],
                    "files": [
                        {
                            "role": "Parser",
                            "path": "Dockerfile",
                            "startLine": 1,
                            "summary": "Updates base image.",
                        }
                    ],
                }
            ],
        }

        node_harness = f"""
const vm = require('vm');
const valid = {json.dumps(valid)};
const minimal = {json.dumps(minimal)};

function makeEl(tag) {{
  const el = {{
    tagName: String(tag || 'DIV').toUpperCase(),
    children: [],
    attrs: {{}},
    className: '',
    textContent: '',
    value: '',
    checked: false,
    disabled: false,
    classList: {{
      _set: new Set(),
      add(c) {{ this._set.add(c); }},
      remove(c) {{ this._set.delete(c); }},
      toggle(c, f) {{ if (f === undefined) {{ if (this._set.has(c)) this._set.delete(c); else this._set.add(c); }} else if (f) this._set.add(c); else this._set.delete(c); }},
      contains(c) {{ return this._set.has(c); }}
    }},
    dataset: {{}},
    style: {{}},
    setAttribute(k, v) {{ this.attrs[k] = String(v); }},
    getAttribute(k) {{ return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }},
    removeAttribute(k) {{ delete this.attrs[k]; }},
    append(...nodes) {{
      for (const n of nodes) {{
        if (n == null || n === false) continue;
        this.children.push(typeof n === 'string' ? {{ nodeType: 3, textContent: n }} : n);
      }}
    }},
    replaceChildren(...nodes) {{
      this.children = [];
      this.append(...nodes);
    }},
    querySelector(sel) {{ return this.querySelectorAll(sel)[0] || null; }},
    querySelectorAll(sel) {{
      const out = [];
      const walk = (node) => {{
        if (!node || !node.children) return;
        for (const c of node.children) {{
          if (c.tagName) {{
            if (sel === c.tagName.toLowerCase() || (sel.startsWith('.') && (c.className || '').split(/\\s+/).includes(sel.slice(1)))) {{
              out.push(c);
            }}
            walk(c);
          }}
        }}
      }};
      walk(this);
      return out;
    }},
    addEventListener() {{}},
  }};
  return el;
}}

const appEl = makeEl('div');
appEl.id = 'app';
const dataEl = makeEl('script');
dataEl.id = 'walkthrough-data';
dataEl.textContent = JSON.stringify(valid);

const storage = new Map();
const sandbox = {{
  document: {{
    documentElement: makeEl('html'),
    body: makeEl('body'),
    title: '',
    getElementById(id) {{ return id === 'walkthrough-data' ? dataEl : id === 'app' ? appEl : null; }},
    createElement: (t) => makeEl(t),
    createElementNS: (_ns, t) => makeEl(t),
    createTextNode: (t) => ({{ nodeType: 3, textContent: String(t) }}),
    querySelectorAll: (sel) => appEl.querySelectorAll(sel),
  }},
  localStorage: {{
    getItem: (k) => storage.has(k) ? storage.get(k) : null,
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k),
  }},
  navigator: {{}},
  location: {{ hash: '' }},
  history: {{ replaceState() {{}} }},
  addEventListener() {{}},
  window: {{ scrollTo() {{}} }},
  setTimeout: () => 0,
  Error, Array, Object, String, Number, Boolean, Set, JSON, RegExp, Math, encodeURIComponent,
}};

// Expose check and build for direct assertions by appending to a patched script copy
const rawScript = {json.dumps(script)};
const patched = rawScript.replace(
  'try{{D=JSON.parse',
  'globalThis.__rwCheck=check;globalThis.__rwBuild=build;globalThis.__rwFail=fail;try{{D=JSON.parse'
);
vm.runInNewContext(patched, sandbox);

const check = sandbox.__rwCheck;
if (typeof check !== 'function') throw new Error('check() missing');

// 1. Valid & minimal v3 pass
check(valid);
check(minimal);

// 2. Reject v2, missing overview, empty slices, duplicate/bad IDs, empty slice refs, empty crossCutting, prefix prose, bad paths
const expectFail = (name, mutator) => {{
  const copy = JSON.parse(JSON.stringify(valid));
  mutator(copy);
  let threw = false;
  try {{ check(copy); }} catch (e) {{ threw = true; }}
  if (!threw) throw new Error('Expected check() to fail for: ' + name);
}};

expectFail('v2', d => {{ d.schemaVersion = 2; }});
expectFail('missing overview', d => {{ delete d.overview; }});
expectFail('empty slices', d => {{ d.slices = []; }});
expectFail('non-kebab slice id', d => {{ d.slices[0].id = 'Bad_Id'; }});
expectFail('duplicate slice id', d => {{ d.slices[1].id = d.slices[0].id; }});
expectFail('empty slice files', d => {{ d.slices[0].files = []; }});
expectFail('empty slice summary', d => {{ d.slices[0].summary = []; }});
expectFail('empty slice headsUp refs', d => {{ d.slices[0].headsUp[0].refs = []; }});
expectFail('empty crossCutting', d => {{ d.crossCutting = {{ headsUp: [], qa: [] }}; }});
expectFail('prefix prose in file summary', d => {{ d.slices[0].files[0].summary = '(a.ts:1): Bad'; }});
expectFail('prefix prose in headsUp body', d => {{ d.slices[0].headsUp[0].body = '(a.ts:1) Bad'; }});
expectFail('traversal in skim', d => {{ d.overview.skim = ['../secret']; }});
expectFail('dot segment in ref', d => {{ d.slices[0].files[0].path = 'src/./a.ts'; }});
expectFail('empty markdownPath', d => {{ d.meta.markdownPath = ''; }});
expectFail('empty defaultEditor', d => {{ d.repo.defaultEditor = ''; }});

// 3. Verify rendered DOM structure in appEl (no footer, has header, overview, slices, crossCutting)
const textDump = (node) => {{
  if (!node) return '';
  if (node.nodeType === 3) return node.textContent || '';
  return (node.textContent || '') + ' ' + (node.children || []).map(textDump).join(' ');
}};
const tags = [];
const collectTags = (node) => {{
  if (!node || !node.children) return;
  for (const c of node.children) {{
    if (c.tagName) {{
      tags.push(c.tagName);
      collectTags(c);
    }}
  }}
}};
collectTags(appEl);
if (tags.includes('FOOTER')) throw new Error('Rendered DOM must not contain <footer>');
if (!tags.includes('HEADER')) throw new Error('Rendered DOM must contain <header>');
const dumped = textDump(appEl);
if (!dumped.includes('a1b2c3d')) throw new Error('Header missing headSha');
if (!dumped.includes('walkthrough.md')) throw new Error('Header missing markdown filename');
if (!dumped.includes('Token Refresh Flow')) throw new Error('Missing title');
if (!dumped.includes('Deduplicate concurrent token refresh')) throw new Error('Missing slice 1');
if (!dumped.includes('Evict stale credentials on failure')) throw new Error('Missing slice 2');
if (!dumped.includes('Cross-Cutting Notes')) throw new Error('Missing crossCutting');

// 4. Verify invalid payload renders invalid-data card without crashing
dataEl.textContent = JSON.stringify({{ schemaVersion: 2 }});
appEl.children = [];
vm.runInNewContext(patched, sandbox);
if (!textDump(appEl).includes('Invalid walkthrough data')) {{
  throw new Error('Malformed payload did not render invalid-data card');
}}
console.log('NODE_TEMPLATE_OK');
"""
        res = subprocess.run(
            ["node", "-e", node_harness],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"Node template check failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
        )
        self.assertIn("NODE_TEMPLATE_OK", res.stdout)


if __name__ == "__main__":
    unittest.main()
