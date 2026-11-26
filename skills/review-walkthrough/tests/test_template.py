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
            28,
            f"Template size is {size_kb:.1f} KB, expected < 28 KB without base64 bloat",
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

    def test_layout_sticky_section_headers_no_fixed_no_qj_and_prog_font(self):
        css = re.search(r"<style>(.*?)</style>", self.content, re.DOTALL).group(1)
        self.assertNotRegex(css, r"position\s*:\s*fixed")
        self.assertNotRegex(css, r"\.hdr\{[^}]*position\s*:\s*sticky")
        self.assertRegex(
            css,
            r"\.sl-h\{[^}]*position\s*:\s*sticky[^}]*top\s*:\s*0[^}]*background\s*:\s*var\(--surface\)",
        )
        self.assertNotRegex(css, r"\.card\{[^}]*overflow\s*:\s*hidden")
        self.assertRegex(css, r"\.sl-prog\{[^}]*var\(--font\)")
        self.assertNotRegex(css, r"\.sl-prog\{[^}]*var\(--mono\)")
        self.assertNotIn(".qj", self.content)
        self.assertNotIn("qj-pill", self.content)
        self.assertNotIn("letter-spacing", css)
        self.assertNotIn("text-transform", css)
        self.assertIn("max-width:780px", css)
        self.assertNotIn("<footer", self.content)
        self.assertNotIn("h('footer'", self.content)
        self.assertNotIn(".card[hidden]", self.content)
        self.assertIn("shaHint", self.content)
        self.assertIn(".sl-body[hidden]{display:block!important}", css)
        self.assertIn(".sl-tog svg{display:none!important}", css)
        self.assertRegex(css, r"\.icon-btn\{")
        print_blocks = re.findall(r"@media print\{(.*)\}", css)
        self.assertTrue(print_blocks, "Expected @media print blocks")
        pb = "\n".join(print_blocks)
        self.assertRegex(pb, r"\.sl-h\{[^}]*position\s*:\s*static")
        self.assertIn(".icon-btn", pb)

    def test_print_rules_allow_card_flow_and_keep_atomic_items(self):
        css = re.search(r"<style>(.*?)</style>", self.content, re.DOTALL).group(1)
        print_blocks = re.findall(r"@media print\{(.*)\}", css)
        self.assertTrue(print_blocks, "Expected @media print blocks")
        pb = "\n".join(print_blocks)
        self.assertNotRegex(pb, r"\.card\{[^}]*break-inside\s*:\s*avoid")
        self.assertRegex(pb, r"\.hu-item[^}]*break-inside\s*:\s*avoid")
        self.assertRegex(pb, r"\.co[^}]*break-inside\s*:\s*avoid")
        self.assertRegex(pb, r"ul\.chk li[^}]*break-inside\s*:\s*avoid")
        self.assertRegex(pb, r"break-after\s*:\s*avoid")

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
    parentNode: null,
    children: [],
    attrs: {{}},
    className: '',
    textContent: '',
    value: '',
    selected: false,
    checked: false,
    disabled: false,
    hidden: false,
    classList: {{
      _set: new Set(),
      add(c) {{ this._set.add(c); }},
      remove(c) {{ this._set.delete(c); }},
      toggle(c, f) {{ if (f === undefined) {{ if (this._set.has(c)) this._set.delete(c); else this._set.add(c); }} else if (f) this._set.add(c); else this._set.delete(c); }},
      contains(c) {{ return this._set.has(c); }}
    }},
    dataset: {{}},
    style: {{}},
    setAttribute(k, v) {{ this.attrs[k] = String(v); if (k === 'id') this.id = String(v); }},
    getAttribute(k) {{ return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }},
    removeAttribute(k) {{ delete this.attrs[k]; }},
    append(...nodes) {{
      for (const n of nodes) {{
        if (n == null || n === false) continue;
        const ch = typeof n === 'string' ? {{ nodeType: 3, textContent: n, parentNode: this }} : n;
        ch.parentNode = this;
        this.children.push(ch);
      }}
    }},
    replaceChildren(...nodes) {{
      this.children = [];
      this.append(...nodes);
    }},
    replaceWith(n) {{
      if (!this.parentNode) return;
      const idx = this.parentNode.children.indexOf(this);
      if (idx >= 0) {{
        n.parentNode = this.parentNode;
        this.parentNode.children[idx] = n;
        this.parentNode = null;
      }}
    }},
    querySelector(sel) {{ return this.querySelectorAll(sel)[0] || null; }},
    querySelectorAll(sel) {{
      const out = [];
      const match = (c) => {{
        const cls = (c.className || '').split(/\\s+/);
        if (sel.startsWith('.')) return sel.slice(1).split('.').every(k => cls.includes(k));
        const dotIdx = sel.indexOf('.');
        if (dotIdx > 0) {{
          return c.tagName.toLowerCase() === sel.slice(0, dotIdx) && sel.slice(dotIdx + 1).split('.').every(k => cls.includes(k));
        }}
        return sel === c.tagName.toLowerCase();
      }};
      const walk = (node) => {{
        if (!node || !node.children) return;
        for (const c of node.children) {{
          if (c.tagName) {{
            if (match(c)) {{
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

// 3a. Quick-jump bar must NOT render even when slices.length > 2
if (appEl.querySelectorAll('.qj').length !== 0) {{
  throw new Error('Quick-jump bar must NOT render');
}}
const threeSlices = JSON.parse(JSON.stringify(valid));
threeSlices.slices.push({{
  id: 'audit-logging',
  title: 'Emit refresh audit logs',
  summary: ['Logs token refresh outcomes.'],
  files: [{{ role: 'Logger', path: 'src/audit.ts', startLine: 1, summary: 'Adds audit events.' }}]
}});
dataEl.textContent = JSON.stringify(threeSlices);
appEl.children = [];
vm.runInNewContext(patched, sandbox);
if (appEl.querySelectorAll('.qj').length !== 0 || appEl.querySelectorAll('.qj-pill').length !== 0) {{
  throw new Error('Quick-jump bar must NEVER render');
}}

// 3b. Slices collapsed by default, full-header button inside <h2 class="sl-h">, live progress, never auto-toggle, & rw-expanded persistence
storage.clear();
dataEl.textContent = JSON.stringify(valid);
appEl.children = [];
vm.runInNewContext(patched, sandbox);

const sliceEls = appEl.querySelectorAll('.slice');
if (sliceEls.length !== 2) throw new Error('Expected 2 slice elements');
const s1H = sliceEls[0].querySelector('h2.sl-h');
const s1Tog = s1H && s1H.querySelector('button.sl-tog');
const s1Body = sliceEls[0].querySelector('.sl-body');
const s1Prog = sliceEls[0].querySelector('.sl-prog');
const s2Tog = sliceEls[1].querySelector('h2.sl-h').querySelector('button.sl-tog');
const s2Body = sliceEls[1].querySelector('.sl-body');
const s2Prog = sliceEls[1].querySelector('.sl-prog');

if (!s1H || !s1Tog || !s1Body || !s1Prog) throw new Error('Slice 1 missing h2.sl-h / button.sl-tog / body / prog');
if (s1Tog.getAttribute('type') !== 'button') throw new Error('Slice toggle must be button[type=button]');
if (s1Tog.getAttribute('aria-controls') !== s1Body.getAttribute('id')) throw new Error('Slice toggle aria-controls must match body id');
if (s1Tog.getAttribute('aria-expanded') !== 'false' || s1Body.hidden !== true) {{
  throw new Error('Slice 1 must start collapsed by default');
}}
if (s2Tog.getAttribute('aria-expanded') !== 'false' || s2Body.hidden !== true) {{
  throw new Error('Slice 2 must start collapsed by default');
}}
if (s1Prog.textContent !== '0/2') throw new Error('Expected Slice 1 progress 0/2, got ' + s1Prog.textContent);
if (s2Prog.textContent !== '0/1') throw new Error('Expected Slice 2 progress 0/1, got ' + s2Prog.textContent);

// Expand Slice 1 -> persists in rw-expanded:a1b2c3d
s1Tog.onclick();
if (s1Tog.getAttribute('aria-expanded') !== 'true' || s1Body.hidden !== false) {{
  throw new Error('Slice 1 should be expanded after toggle');
}}
const savedExpanded = JSON.parse(storage.get('rw-expanded:a1b2c3d') || '[]');
if (savedExpanded.length !== 1 || savedExpanded[0] !== 'token-refresh') {{
  throw new Error('Unexpected rw-expanded persistence: ' + JSON.stringify(savedExpanded));
}}

// Check file 0 in Slice 1 -> updates progress, never auto-collapses, does not affect Slice 2
const s1Checks = sliceEls[0].querySelectorAll('input');
s1Checks[0].checked = true;
s1Checks[0].onchange();
if (s1Prog.textContent !== '1/2') throw new Error('Expected Slice 1 progress 1/2 after check, got ' + s1Prog.textContent);
if (s1Tog.getAttribute('aria-expanded') !== 'true' || s1Body.hidden !== false) {{
  throw new Error('Checking item must NEVER auto-collapse slice');
}}
const savedFiles = JSON.parse(storage.get('rw-files:a1b2c3d') || '[]');
if (savedFiles.length !== 1 || savedFiles[0] !== 'token-refresh:0') {{
  throw new Error('Unexpected rw-files persistence: ' + JSON.stringify(savedFiles));
}}

// Reload with persisted storage -> Slice 1 stays expanded with 1/2, Slice 2 stays collapsed & unchecked
appEl.children = [];
vm.runInNewContext(patched, sandbox);
const reloadedSlices = appEl.querySelectorAll('.slice');
if (reloadedSlices[0].querySelector('.sl-tog').getAttribute('aria-expanded') !== 'true' || reloadedSlices[0].querySelector('.sl-body').hidden !== false) {{
  throw new Error('Slice 1 expanded state did not persist across reload');
}}
if (reloadedSlices[0].querySelector('.sl-prog').textContent !== '1/2') {{
  throw new Error('Slice 1 progress did not persist across reload');
}}
if (reloadedSlices[1].querySelector('.sl-tog').getAttribute('aria-expanded') !== 'false' || reloadedSlices[1].querySelector('.sl-body').hidden !== true) {{
  throw new Error('Slice 2 should remain collapsed');
}}
if (reloadedSlices[1].querySelector('input').checked !== false) {{
  throw new Error('Slice 2 same-path file must remain unchecked');
}}
// Collapse Slice 1 again -> removes from rw-expanded:a1b2c3d
reloadedSlices[0].querySelector('.sl-tog').onclick();
const afterCollapse = JSON.parse(storage.get('rw-expanded:a1b2c3d') || '[]');
if (afterCollapse.length !== 0) {{
  throw new Error('Collapsing Slice 1 should remove it from rw-expanded, got ' + JSON.stringify(afterCollapse));
}}

// 3b2. Collapsible Overview & Cross-Cutting (open by default, rw-collapsed persistence, & Cross-Cutting .sl-prog)
storage.clear();
dataEl.textContent = JSON.stringify(valid);
appEl.children = [];
vm.runInNewContext(patched, sandbox);

const ovEl = appEl.querySelector('.ov');
const ovH = ovEl.querySelector('h2.sl-h');
const ovTog = ovH && ovH.querySelector('button.sl-tog');
const ovBody = ovEl.querySelector('.sl-body');
if (!ovH || !ovTog || !ovBody) throw new Error('Overview missing h2.sl-h / button.sl-tog / .sl-body');
if (ovTog.getAttribute('type') !== 'button') throw new Error('Overview toggle must be button[type=button]');
if (ovTog.getAttribute('aria-controls') !== ovBody.getAttribute('id')) throw new Error('Overview aria-controls mismatch');
if (ovTog.getAttribute('aria-expanded') !== 'true' || ovBody.hidden !== false) {{
  throw new Error('Overview must start expanded by default');
}}
if (ovEl.querySelector('.sl-prog')) throw new Error('Overview must not render .sl-prog');

const ccEl = appEl.querySelector('.cc');
const ccH = ccEl.querySelector('h2.sl-h');
const ccTog = ccH && ccH.querySelector('button.sl-tog');
const ccBody = ccEl.querySelector('.sl-body');
const ccProg = ccEl.querySelector('.sl-prog');
if (!ccH || !ccTog || !ccBody || !ccProg) throw new Error('Cross-Cutting missing h2.sl-h / button.sl-tog / .sl-body / .sl-prog');
if (ccTog.getAttribute('type') !== 'button') throw new Error('Cross-Cutting toggle must be button[type=button]');
if (ccTog.getAttribute('aria-controls') !== ccBody.getAttribute('id')) throw new Error('Cross-Cutting aria-controls mismatch');
if (ccTog.getAttribute('aria-expanded') !== 'true' || ccBody.hidden !== false) {{
  throw new Error('Cross-Cutting must start expanded by default');
}}
if (ccProg.textContent !== '0/1') throw new Error('Expected Cross-Cutting progress 0/1, got ' + ccProg.textContent);

// Toggling Cross-Cutting QA checkbox updates .sl-prog without collapsing
const ccQaBox = ccEl.querySelector('input');
ccQaBox.checked = true;
ccQaBox.onchange();
if (ccProg.textContent !== '1/1') throw new Error('Expected Cross-Cutting progress 1/1 after check, got ' + ccProg.textContent);
if (ccTog.getAttribute('aria-expanded') !== 'true' || ccBody.hidden !== false) {{
  throw new Error('Checking Cross-Cutting QA must not collapse section');
}}

// Collapse both Overview and Cross-Cutting -> persist in rw-collapsed:a1b2c3d
ovTog.onclick();
ccTog.onclick();
if (ovTog.getAttribute('aria-expanded') !== 'false' || ovBody.hidden !== true) {{
  throw new Error('Overview should collapse on click');
}}
if (ccTog.getAttribute('aria-expanded') !== 'false' || ccBody.hidden !== true) {{
  throw new Error('Cross-Cutting should collapse on click');
}}
const savedOvCcCollapsed = JSON.parse(storage.get('rw-collapsed:a1b2c3d') || '[]');
if (!savedOvCcCollapsed.includes('overview') || !savedOvCcCollapsed.includes('cross-cutting')) {{
  throw new Error('Unexpected rw-collapsed for overview/cross-cutting: ' + JSON.stringify(savedOvCcCollapsed));
}}

// Reload -> Overview and Cross-Cutting stay collapsed, and Cross-Cutting progress stays 1/1
appEl.children = [];
vm.runInNewContext(patched, sandbox);
if (appEl.querySelector('.ov').querySelector('.sl-tog').getAttribute('aria-expanded') !== 'false' || appEl.querySelector('.ov').querySelector('.sl-body').hidden !== true) {{
  throw new Error('Overview collapsed state did not persist across reload');
}}
if (appEl.querySelector('.cc').querySelector('.sl-tog').getAttribute('aria-expanded') !== 'false' || appEl.querySelector('.cc').querySelector('.sl-body').hidden !== true) {{
  throw new Error('Cross-Cutting collapsed state did not persist across reload');
}}
if (appEl.querySelector('.cc').querySelector('.sl-prog').textContent !== '1/1') {{
  throw new Error('Cross-Cutting progress did not persist across reload');
}}

// Re-expand Overview -> removes overview from rw-collapsed
appEl.querySelector('.ov').querySelector('.sl-tog').onclick();
const afterOvExpand = JSON.parse(storage.get('rw-collapsed:a1b2c3d') || '[]');
if (afterOvExpand.includes('overview') || !afterOvExpand.includes('cross-cutting')) {{
  throw new Error('Re-expanding Overview should remove only overview from rw-collapsed: ' + JSON.stringify(afterOvExpand));
}}

// Cross-Cutting without qa omits .sl-prog
const ccNoQaPayload = JSON.parse(JSON.stringify(valid));
ccNoQaPayload.crossCutting.qa = [];
storage.clear();
dataEl.textContent = JSON.stringify(ccNoQaPayload);
appEl.children = [];
vm.runInNewContext(patched, sandbox);
if (appEl.querySelector('.cc').querySelector('.sl-prog')) {{
  throw new Error('Cross-Cutting without QA items must not render .sl-prog');
}}

// Restore valid payload with clean storage for subsequent tests
storage.clear();
dataEl.textContent = JSON.stringify(valid);
appEl.children = [];
vm.runInNewContext(patched, sandbox);

// 3c. QA persistence across slice & crossCutting, duplicate basename disambiguation, IDE URLs, print beforeprint/afterprint, & RTL
const s1QaCheck = reloadedSlices[0].querySelectorAll('input')[1];
s1QaCheck.checked = true;
s1QaCheck.onchange();
const ccQaCheck = appEl.querySelector('.cc').querySelector('input');
ccQaCheck.checked = true;
ccQaCheck.onchange();
const savedQa = JSON.parse(storage.get('rw-qa:a1b2c3d') || '[]');
if (!savedQa.includes('token-refresh:0') || !savedQa.includes('cross-cutting:0')) {{
  throw new Error('Unexpected rw-qa persistence: ' + JSON.stringify(savedQa));
}}

// Duplicate basename disambiguation across slice + crossCutting
const dupPayload = JSON.parse(JSON.stringify(valid));
dupPayload.slices[0].files.push({{ role: 'Index A', path: 'src/a/index.ts', startLine: 1, summary: 'Module A.' }});
dupPayload.crossCutting.headsUp[0].refs = [{{ path: 'src/b/index.ts', startLine: 5 }}];
dataEl.textContent = JSON.stringify(dupPayload);
appEl.children = [];
vm.runInNewContext(patched, sandbox);
const dupDump = textDump(appEl);
if (!dupDump.includes('…/a/index.ts:1') || !dupDump.includes('…/b/index.ts:5')) {{
  throw new Error('Duplicate basename disambiguation failed across slices/crossCutting');
}}

// Print beforeprint / afterprint opens & restores <details class="skim">
const skimEl = appEl.querySelector('details');
if (!skimEl) throw new Error('Expected <details class="skim">');
if (skimEl.open) throw new Error('Skim <details> must start closed');
const listeners = {{}};
const printSandbox = Object.assign({{}}, sandbox, {{
  addEventListener: (ev, fn) => {{ (listeners[ev] = listeners[ev] || []).push(fn); }},
}});
appEl.children = [];
vm.runInNewContext(patched, printSandbox);
const skimPrint = appEl.querySelector('details');
if (!listeners.beforeprint || !listeners.beforeprint.length) {{
  throw new Error('Expected beforeprint listener for auto-expanding skim details');
}}
listeners.beforeprint.forEach(fn => fn());
if (!skimPrint.open) throw new Error('beforeprint must open <details class="skim">');
if (listeners.afterprint) listeners.afterprint.forEach(fn => fn());
if (skimPrint.open) throw new Error('afterprint must restore closed <details class="skim">');

// RTL Persian rendering in Node
const faPayload = {{
  schemaVersion: 3,
  lang: 'fa',
  meta: {{ title: 'بازبینی review-walkthrough v4.0.0 و **Vertical Slice**', branch: 'feat/rtl', base: 'main', headSha: 'ff00aa1', stats: {{ files: 3, added: 5, removed: 1 }} }},
  overview: {{ title: 'نمای کلی Schema v3: خروجی HTML/Markdown', affects: 'بخش A → B، API, و `build()`', skim: ['README.md'] }},
  slices: [{{
    id: 'rtl-slice-1',
    title: 'بخش Vertical Slice اول',
    summary: ['توضیح Schema v3 در `build()` و جستجوی Ctrl+F برای بخش اول.'],
    files: [{{ role: 'سرویس', path: 'src/a.ts', startLine: 1, summary: 'تغییر A → B' }}],
    headsUp: [{{
      title: 'نکته review-walkthrough v4.0.0: ترتیب کلمات',
      body: 'این عبارت Schema v3 نباید برعکس بشه.',
      refs: [{{ path: 'src/a.ts', startLine: 1 }}],
      lookFor: 'بررسی Vertical Slice در خروجی'
    }}],
    qa: ['تست خروجی HTML/Markdown با `edUrl()`']
  }}, {{
    id: 'rtl-slice-2',
    title: 'بخش دوم',
    summary: ['خلاصه دوم'],
    files: [
      {{ role: 'دوم', path: 'src/b.ts', startLine: 1, status: 'added', summary: 'فایل دوم.' }},
      {{ role: 'حذف‌شده', path: 'src/old.ts', startLine: 1, status: 'deleted', summary: 'فایل قدیمی.' }}
    ]
  }}, {{
    id: 'rtl-slice-3',
    title: 'بخش سوم',
    summary: ['خلاصه سوم'],
    files: [{{ role: 'سوم', path: 'src/c.ts', startLine: 1, summary: 'فایل سوم.' }}]
  }}],
  crossCutting: {{
    headsUp: [{{ title: 'نکته سراسری', body: 'بررسی سراسری.', refs: [] }}],
    qa: ['بررسی کلی RTL']
  }}
}};
storage.clear();
dataEl.textContent = JSON.stringify(faPayload);
appEl.children = [];
vm.runInNewContext(patched, sandbox);
if (sandbox.document.documentElement.dir !== 'rtl') throw new Error('Expected dir=rtl for fa');
const faProg = appEl.querySelector('.sl-prog').textContent;
if (faProg !== '۰/۲') throw new Error('Expected Persian digits ۰/۲ in progress, got ' + faProg);
const faCcProg = appEl.querySelector('.cc').querySelector('.sl-prog');
if (!faCcProg || faCcProg.textContent !== '۰/۱') throw new Error('Expected Persian digits ۰/۱ in Cross-Cutting progress, got ' + (faCcProg && faCcProg.textContent));
const faDump = textDump(appEl);
if (!faDump.includes('←')) throw new Error('Expected RTL arrow ← in Persian render');

const bdiTexts = appEl.querySelectorAll('bdi').map(b => b.textContent);
const bdiDirs = appEl.querySelectorAll('bdi').map(b => b.getAttribute('dir'));
if (bdiDirs.some(d => d !== 'ltr')) {{
  throw new Error('Every <bdi> in RTL rich() must have dir="ltr", got: ' + JSON.stringify(bdiDirs));
}}
for (const phrase of ['review-walkthrough v4.0.0', 'Vertical Slice', 'Schema v3', 'HTML/Markdown', 'Ctrl+F']) {{
  if (!bdiTexts.includes(phrase)) {{
    throw new Error('Expected contiguous <bdi dir="ltr"> for "' + phrase + '", got: ' + JSON.stringify(bdiTexts));
  }}
}}
if (bdiTexts.some(t => /[:,]$/.test(t))) {{
  throw new Error('Trailing punctuation (: or ,) must stay outside <bdi>, got: ' + JSON.stringify(bdiTexts));
}}
const strongBdis = appEl.querySelector('h1').querySelectorAll('strong bdi').length
  ? appEl.querySelector('h1').querySelectorAll('strong bdi')
  : appEl.querySelector('h1').querySelector('strong').querySelectorAll('bdi');
if (!strongBdis.length || strongBdis[0].textContent !== 'Vertical Slice' || strongBdis[0].getAttribute('dir') !== 'ltr') {{
  throw new Error('Expected **Vertical Slice** to wrap <bdi dir="ltr"> inside <strong>');
}}
const codeEls = appEl.querySelectorAll('code').map(c => ({{ text: c.textContent, dir: c.getAttribute('dir') }}));
if (!codeEls.some(c => c.text === 'build()' && c.dir === 'ltr') || !codeEls.some(c => c.text === 'edUrl()' && c.dir === 'ltr')) {{
  throw new Error('Expected backticked code spans as <code dir="ltr">, got: ' + JSON.stringify(codeEls));
}}
const slice1Bdi = appEl.querySelector('.slice').querySelector('.sl-tit').querySelector('bdi');
if (!slice1Bdi || slice1Bdi.textContent !== 'Vertical Slice' || slice1Bdi.getAttribute('dir') !== 'ltr') {{
  throw new Error('Expected slice title to keep Vertical Slice in one <bdi dir="ltr">');
}}
const faEdSel = appEl.querySelector('.ed-sel');
if (faEdSel.getAttribute('aria-label') !== 'ویرایشگر') {{
  throw new Error('Expected Persian aria-label ویرایشگر on .ed-sel, got ' + faEdSel.getAttribute('aria-label'));
}}
const faBrowserBtn = appEl.querySelector('.hdr').querySelector('a.icon-btn');
if (!faBrowserBtn || faBrowserBtn.getAttribute('aria-label') !== 'باز کردن در مرورگر' || faBrowserBtn.getAttribute('title') !== 'باز کردن در مرورگر') {{
  throw new Error('Expected Persian open-in-browser label on .hdr a.icon-btn, got ' + (faBrowserBtn && faBrowserBtn.getAttribute('aria-label')));
}}
const faAddDot = appEl.querySelector('.std.add');
const faDelDot = appEl.querySelector('.std.del');
if (!faAddDot || faAddDot.getAttribute('title') !== 'اضافه‌شده') {{
  throw new Error('Expected localized added dot title اضافه‌شده, got ' + (faAddDot && faAddDot.getAttribute('title')));
}}
if (!faDelDot || faDelDot.getAttribute('title') !== 'حذف‌شده') {{
  throw new Error('Expected localized deleted dot title حذف‌شده, got ' + (faDelDot && faDelDot.getAttribute('title')));
}}

// 3d. Deleted file pill integrity on IDE switch
const delPayload = JSON.parse(JSON.stringify(valid));
delPayload.slices[0].files.push({{
  role: 'Removed helper',
  path: 'src/auth/legacy.ts',
  startLine: 10,
  status: 'deleted',
  summary: 'Legacy token helper removed.'
}}, {{
  role: 'Added helper',
  path: 'src/auth/fresh.ts',
  startLine: 5,
  status: 'added',
  summary: 'New token helper added.'
}});
storage.clear();
dataEl.textContent = JSON.stringify(delPayload);
appEl.children = [];
vm.runInNewContext(patched, sandbox);
const edSel = appEl.querySelector('.ed-sel');
if (!edSel) throw new Error('Expected .ed-sel');
if (edSel.getAttribute('aria-label') !== 'Editor') {{
  throw new Error('Expected English aria-label Editor on .ed-sel, got ' + edSel.getAttribute('aria-label'));
}}
const enBrowserBtn = appEl.querySelector('.hdr').querySelector('a.icon-btn');
if (!enBrowserBtn || enBrowserBtn.getAttribute('aria-label') !== 'Open in browser' || enBrowserBtn.getAttribute('title') !== 'Open in browser') {{
  throw new Error('Expected English open-in-browser label on .hdr a.icon-btn');
}}
if (enBrowserBtn.getAttribute('target') !== '_blank' || !String(enBrowserBtn.getAttribute('rel') || '').includes('noopener')) {{
  throw new Error('Expected target=_blank and rel=noopener on .hdr a.icon-btn');
}}
if (enBrowserBtn.getAttribute('href') !== 'file:///tmp/walkthrough.html') {{
  throw new Error('Expected file:// fallback href from markdownPath, got ' + enBrowserBtn.getAttribute('href'));
}}
let openedArgs = null;
const browserSandbox = Object.assign({{}}, sandbox, {{
  location: {{ hash: '', href: 'https://review.local/walkthrough.html' }},
  window: {{ scrollTo() {{}}, open(...args) {{ openedArgs = args; return {{}}; }} }},
}});
dataEl.textContent = JSON.stringify(valid);
appEl.children = [];
vm.runInNewContext(patched, browserSandbox);
const liveBtn = appEl.querySelector('.hdr').querySelector('a.icon-btn');
if (!liveBtn || liveBtn.getAttribute('href') !== 'https://review.local/walkthrough.html') {{
  throw new Error('Expected current location.href on .hdr a.icon-btn, got ' + (liveBtn && liveBtn.getAttribute('href')));
}}
liveBtn.onclick({{ preventDefault() {{}} }});
if (!openedArgs || openedArgs[0] !== 'https://review.local/walkthrough.html' || openedArgs[1] !== '_blank' || !String(openedArgs[2] || '').includes('noopener')) {{
  throw new Error('Expected window.open with _blank and noopener, got ' + JSON.stringify(openedArgs));
}}
const fallbackSandbox = Object.assign({{}}, sandbox, {{
  location: {{ hash: '', href: 'https://review.local/walkthrough.html' }},
  window: {{ scrollTo() {{}}, open() {{ return null; }} }},
}});
appEl.children = [];
vm.runInNewContext(patched, fallbackSandbox);
appEl.querySelector('.hdr').querySelector('a.icon-btn').onclick({{ preventDefault() {{}} }});
if (fallbackSandbox.location.href !== 'googlechrome://review.local/walkthrough.html') {{
  throw new Error('Expected Chrome fallback URL when window.open returns null, got ' + fallbackSandbox.location.href);
}}
dataEl.textContent = JSON.stringify(delPayload);
appEl.children = [];
vm.runInNewContext(patched, sandbox);
const enAddDot = appEl.querySelector('.std.add');
const enDelDot = appEl.querySelector('.std.del');
if (!enAddDot || enAddDot.getAttribute('title') !== 'Added') {{
  throw new Error('Expected English added dot title Added, got ' + (enAddDot && enAddDot.getAttribute('title')));
}}
if (!enDelDot || enDelDot.getAttribute('title') !== 'Deleted') {{
  throw new Error('Expected English deleted dot title Deleted, got ' + (enDelDot && enDelDot.getAttribute('title')));
}}
const checkDeletedPill = (expectedSchemePrefix) => {{
  const pills = appEl.querySelectorAll('.ref-pill');
  const modPill = pills.find(p => p.getAttribute('data-path') === 'src/auth/token.ts');
  const addPill = pills.find(p => p.getAttribute('data-path') === 'src/auth/fresh.ts');
  const delPill = pills.find(p => p.getAttribute('data-path') === 'src/auth/legacy.ts');
  if (!modPill || !addPill || !delPill) throw new Error('Missing expected ref pills');
  const modA = modPill.querySelector('a.rl');
  const addA = addPill.querySelector('a.rl');
  if (!modA || !modA.getAttribute('href').startsWith(expectedSchemePrefix)) {{
    throw new Error('Expected modified pill href starting with ' + expectedSchemePrefix + ', got ' + (modA && modA.getAttribute('href')));
  }}
  if (!addA || !addA.getAttribute('href').startsWith(expectedSchemePrefix)) {{
    throw new Error('Expected added pill href starting with ' + expectedSchemePrefix + ', got ' + (addA && addA.getAttribute('href')));
  }}
  if (delPill.querySelector('a.rl')) {{
    throw new Error('Deleted file pill must NEVER become <a class="rl">');
  }}
  if (!delPill.querySelector('span.rl')) {{
    throw new Error('Deleted file pill must remain <span class="rl">');
  }}
}};
checkDeletedPill('vscode://file');
edSel.value = 'cursor';
edSel.onchange();
checkDeletedPill('cursor://file');
edSel.value = 'zed';
edSel.onchange();
checkDeletedPill('zed://file');

// 3e. Editor alias parity (webstorm, pycharm, vscode-insiders, vscodium, studio -> android-studio)
const assertActiveEditor = (ctx, expectedVal, expectedLabel, expectedPrefix) => {{
  const sel = appEl.querySelector('.ed-sel');
  const opt = sel.querySelectorAll('option').find(o => o.value === expectedVal || o.getAttribute('value') === expectedVal);
  if (!opt || !opt.selected || opt.textContent !== expectedLabel || sel.value !== expectedVal) {{
    throw new Error(ctx + ' failed select option/state check: ' + JSON.stringify({{ opt, selVal: sel.value }}));
  }}
  const href = appEl.querySelector('.ref-pill').querySelector('a.rl').getAttribute('href');
  if (!href.startsWith(expectedPrefix)) {{
    throw new Error(ctx + ' expected href prefix ' + expectedPrefix + ', got ' + href);
  }}
}};
const aliasCases = [
  ['webstorm', 'webstorm', 'WebStorm', 'webstorm://open?file='],
  ['pycharm', 'pycharm', 'PyCharm', 'pycharm://open?file='],
  ['vscode-insiders', 'vscode-insiders', 'VS Code Insiders', 'vscode-insiders://file'],
  ['vscodium', 'vscodium', 'VSCodium', 'vscodium://file'],
  ['studio', 'android-studio', 'Android Studio', 'idea://open?file='],
];
for (const [inputEd, expectedVal, expectedLabel, expectedPrefix] of aliasCases) {{
  // Via repo.defaultEditor
  storage.clear();
  const p1 = JSON.parse(JSON.stringify(valid));
  p1.repo.defaultEditor = inputEd;
  dataEl.textContent = JSON.stringify(p1);
  appEl.children = [];
  vm.runInNewContext(patched, sandbox);
  assertActiveEditor('defaultEditor=' + inputEd, expectedVal, expectedLabel, expectedPrefix);

  // Via localStorage['rw-editor'] overriding defaultEditor='vscode'
  storage.clear();
  storage.set('rw-editor', inputEd);
  const p2 = JSON.parse(JSON.stringify(valid));
  p2.repo.defaultEditor = 'vscode';
  dataEl.textContent = JSON.stringify(p2);
  appEl.children = [];
  vm.runInNewContext(patched, sandbox);
  assertActiveEditor('localStorage rw-editor=' + inputEd, expectedVal, expectedLabel, expectedPrefix);
}}

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
