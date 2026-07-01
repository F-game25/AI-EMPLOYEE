const assert = require('assert');

process.env.STATE_DIR = process.env.STATE_DIR || require('os').tmpdir();
process.env.PYTHON_BACKEND_PORT = process.env.PYTHON_BACKEND_PORT || '9';

const { extractCodeActions } = require('../backend/routes/forge').__test__;

const project = { id: 'proj-extract-test' };

// Regression: live-verified against the configured FORGE_OLLAMA_MODEL
// (qwythos:q4) — Ollama returns done_reason "stop" right after the code body,
// never emitting the closing ``` fence. The extractor must not silently drop
// that block (previously: zero actions -> run reaches awaiting_approval with
// nothing to approve, no error anywhere).
{
  const text = '```python hello.py\ndef greet(name):\n    """Greet someone."""\n    return f"Hello, {name}!"';
  const actions = extractCodeActions(text, project);
  assert.equal(actions.length, 1, 'dangling unclosed fence must still yield one write_file action');
  assert.equal(actions[0].type, 'write_file');
  assert.equal(actions[0].file_path, 'hello.py');
  assert(actions[0].content.includes('def greet(name):'));
  assert(!actions[0].content.includes('```'), 'fence markers must not leak into file content');
}

// A properly closed fence must still work exactly as before (no regression).
{
  const text = '```python src/app.py\nprint("hi")\n```\n\nDone.';
  const actions = extractCodeActions(text, project);
  assert.equal(actions.length, 1);
  assert.equal(actions[0].file_path, 'src/app.py');
  assert.equal(actions[0].content, 'print("hi")\n');
}

// Mixed: one closed block followed by a second, dangling, unclosed block —
// both must be extracted (the tail scan only looks past the last closed match).
{
  const text = '```js a.js\nconsole.log(1)\n```\n\nNow the second file:\n\n```js b.js\nconsole.log(2)';
  const actions = extractCodeActions(text, project);
  assert.equal(actions.length, 2);
  assert.equal(actions[0].file_path, 'a.js');
  assert.equal(actions[1].file_path, 'b.js');
  assert.equal(actions[1].content, 'console.log(2)');
}

// Trailing prose with no code fence at all after the last closed block must
// not fabricate a phantom action.
{
  const text = '```js a.js\nconsole.log(1)\n```\n\nThat should do it, let me know if you need anything else.';
  const actions = extractCodeActions(text, project);
  assert.equal(actions.length, 1);
}

// No fences anywhere -> no actions (not this extractor's job to guess).
{
  const actions = extractCodeActions('Sure, I can help with that.', project);
  assert.equal(actions.length, 0);
}

// Regression: live-verified against qwythos:q4 via the local codegen benchmark
// (tests/benchmarks, forge_codegen task) — a stray leading space before the
// language token on the fence line (` ``` python calc.py` instead of
// ```` ```python calc.py````) shifted the whole "python calc.py" into the
// fence-hint capture. The path resolver used to take that ENTIRE hint as the
// file path, producing a literal file named "python calc.py" instead of
// "calc.py". Only the matched path-like token must be used.
{
  const text = '``` python calc.py\ndef add(a, b):\n    """Add two numbers."""\n    return a + b\n```';
  const actions = extractCodeActions(text, project);
  assert.equal(actions.length, 1);
  assert.equal(actions[0].file_path, 'calc.py', 'must not include the language token in the path');
}

console.log('[✓] forge codegen extraction (dangling-fence regression) tests passed');
