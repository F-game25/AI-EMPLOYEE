import { useEffect, useState, useRef } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Placeholder from '@tiptap/extension-placeholder';
import { Node, mergeAttributes } from '@tiptap/core';
import './MarkdownEditor.css';

// Slugify wikilink target for resolution lookup (mirrors backend convention)
const slug = (t) => String(t || '').toLowerCase().trim().replace(/\s+/g, '-');

// ── Custom Wikilink node ────────────────────────────────────────────────────
// Renders [[target]] or [[target|label]] as an atomic inline node.
const Wikilink = Node.create({
  name: 'wikilink',
  inline: true,
  group: 'inline',
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      target: { default: '' },
      label: { default: null },
      resolved: { default: false },
    };
  },

  parseHTML() {
    return [{
      tag: 'span[data-wikilink]',
      getAttrs: (el) => ({
        target: el.getAttribute('data-target') || '',
        label: el.textContent || null,
        resolved: el.getAttribute('data-resolved') === 'true',
      }),
    }];
  },

  renderHTML({ HTMLAttributes }) {
    const { target, label, resolved } = HTMLAttributes;
    const cls = `wikilink ${resolved ? 'wikilink--resolved' : 'wikilink--unresolved'}`;
    return ['span', mergeAttributes({
      'data-wikilink': 'true',
      'data-target': target,
      'data-resolved': String(!!resolved),
      class: cls,
    }), label || target];
  },

  addCommands() {
    return {
      insertWikilink: (target, label) => ({ commands }) =>
        commands.insertContent({ type: 'wikilink', attrs: { target, label } }),
    };
  },
});

// ── Markdown ↔ TipTap conversion (lightweight, vault-shape oriented) ────────
function parseMarkdownToContent(markdown, resolvedTargets) {
  const resolved = resolvedTargets instanceof Set ? resolvedTargets : new Set(resolvedTargets || []);
  const lines = String(markdown || '').split('\n');
  const content = [];
  let buffer = [];

  const flushBuffer = () => {
    if (!buffer.length) return;
    const paragraphText = buffer.join(' ');
    const parts = paragraphText.split(/(\[\[[^\]]+\]\])/g);
    const nodes = [];
    for (const part of parts) {
      const m = part.match(/^\[\[([^\]|]+)(?:\|([^\]]+))?\]\]$/);
      if (m) {
        const target = m[1].trim();
        const label = m[2] ? m[2].trim() : null;
        nodes.push({ type: 'wikilink', attrs: { target, label, resolved: resolved.has(slug(target)) } });
      } else if (part) {
        nodes.push({ type: 'text', text: part });
      }
    }
    if (nodes.length) content.push({ type: 'paragraph', content: nodes });
    buffer = [];
  };

  for (const line of lines) {
    if (line.startsWith('# ')) {
      flushBuffer();
      content.push({ type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: line.slice(2) }] });
    } else if (line.startsWith('## ')) {
      flushBuffer();
      content.push({ type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: line.slice(3) }] });
    } else if (line.startsWith('### ')) {
      flushBuffer();
      content.push({ type: 'heading', attrs: { level: 3 }, content: [{ type: 'text', text: line.slice(4) }] });
    } else if (line.trim() === '') {
      flushBuffer();
    } else {
      buffer.push(line);
    }
  }
  flushBuffer();
  return { type: 'doc', content: content.length ? content : [{ type: 'paragraph' }] };
}

function serializeContentToMarkdown(doc) {
  if (!doc?.content) return '';
  const lines = [];
  for (const node of doc.content) {
    if (node.type === 'heading') {
      const prefix = '#'.repeat(node.attrs?.level || 1) + ' ';
      const text = (node.content || []).map((c) => c.text || '').join('');
      lines.push(prefix + text, '');
    } else if (node.type === 'paragraph') {
      const text = (node.content || []).map((c) => {
        if (c.type === 'wikilink') {
          const t = c.attrs?.target || '';
          const l = c.attrs?.label;
          return l && l !== t ? `[[${t}|${l}]]` : `[[${t}]]`;
        }
        return c.text || '';
      }).join('');
      lines.push(text, '');
    } else if (node.type === 'bulletList' || node.type === 'orderedList') {
      let i = 1;
      for (const item of node.content || []) {
        const text = (item.content?.[0]?.content || []).map((c) => c.text || '').join('');
        lines.push((node.type === 'orderedList' ? `${i++}. ` : '- ') + text);
      }
      lines.push('');
    } else if (node.type === 'blockquote') {
      for (const child of node.content || []) {
        const text = (child.content || []).map((c) => c.text || '').join('');
        lines.push('> ' + text);
      }
      lines.push('');
    } else if (node.type === 'codeBlock') {
      lines.push('```');
      lines.push((node.content || []).map((c) => c.text || '').join(''));
      lines.push('```', '');
    }
  }
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

// ── Editor component ────────────────────────────────────────────────────────
export default function MarkdownEditor({
  noteId,
  body = '',
  resolvedTargets,
  onSave,
  onChange,
  allNoteTitles = [],
  placeholder = 'Start writing… use [[ to link notes',
}) {
  const [autocomplete, setAutocomplete] = useState({ active: false, query: '', items: [] });
  const saveTimerRef = useRef(null);
  const lastBodyRef = useRef(body);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Link.configure({ openOnClick: false }),
      Placeholder.configure({ placeholder }),
      Wikilink,
    ],
    content: parseMarkdownToContent(body, resolvedTargets),
    onUpdate: ({ editor: ed }) => {
      const markdown = serializeContentToMarkdown(ed.getJSON());
      lastBodyRef.current = markdown;
      onChange?.(markdown);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => onSave?.(markdown), 800);
    },
  }, [noteId]);

  // Re-hydrate when switching notes or external body changes
  useEffect(() => {
    if (!editor) return;
    if (body !== lastBodyRef.current) {
      lastBodyRef.current = body;
      editor.commands.setContent(parseMarkdownToContent(body, resolvedTargets), false);
    }
  }, [noteId, body, editor, resolvedTargets]);

  // Cleanup pending save timer on unmount
  useEffect(() => () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); }, []);

  // Detect [[ typing → open autocomplete
  useEffect(() => {
    if (!editor) return;
    const update = ({ editor: ed }) => {
      const { $from } = ed.state.selection;
      const textBefore = $from.parent.textBetween(0, $from.parentOffset, ' ', ' ');
      const m = textBefore.match(/\[\[([^\]]*)$/);
      if (m) {
        const query = m[1];
        const q = query.toLowerCase();
        const items = (allNoteTitles || [])
          .filter((t) => t.toLowerCase().includes(q))
          .slice(0, 8);
        setAutocomplete({ active: true, query, items });
      } else if (autocomplete.active) {
        setAutocomplete({ active: false, query: '', items: [] });
      }
    };
    editor.on('selectionUpdate', update);
    editor.on('update', update);
    return () => {
      editor.off('selectionUpdate', update);
      editor.off('update', update);
    };
  }, [editor, allNoteTitles, autocomplete.active]);

  const insertWikilink = (target) => {
    if (!editor) return;
    const { from } = editor.state.selection;
    const lookback = Math.max(0, from - 60);
    const text = editor.state.doc.textBetween(lookback, from, ' ', ' ');
    const m = text.match(/\[\[([^\]]*)$/);
    if (m) {
      const start = from - m[0].length;
      editor.chain().focus().deleteRange({ from: start, to: from }).insertWikilink(target, null).run();
    } else {
      editor.commands.insertWikilink(target, null);
    }
    setAutocomplete({ active: false, query: '', items: [] });
  };

  if (!editor) return null;

  return (
    <div className="md-editor">
      <div className="md-editor__toolbar" role="toolbar" aria-label="Editor formatting">
        <button type="button" onClick={() => editor.chain().focus().toggleBold().run()} className={editor.isActive('bold') ? 'is-active' : ''} aria-pressed={editor.isActive('bold')} aria-label="Bold"><b>B</b></button>
        <button type="button" onClick={() => editor.chain().focus().toggleItalic().run()} className={editor.isActive('italic') ? 'is-active' : ''} aria-pressed={editor.isActive('italic')} aria-label="Italic"><i>I</i></button>
        <button type="button" onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} className={editor.isActive('heading', { level: 1 }) ? 'is-active' : ''} aria-label="Heading 1">H1</button>
        <button type="button" onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} className={editor.isActive('heading', { level: 2 }) ? 'is-active' : ''} aria-label="Heading 2">H2</button>
        <button type="button" onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} className={editor.isActive('heading', { level: 3 }) ? 'is-active' : ''} aria-label="Heading 3">H3</button>
        <span className="md-editor__sep" aria-hidden="true" />
        <button type="button" onClick={() => editor.chain().focus().toggleBulletList().run()} className={editor.isActive('bulletList') ? 'is-active' : ''} aria-label="Bullet list">•</button>
        <button type="button" onClick={() => editor.chain().focus().toggleOrderedList().run()} className={editor.isActive('orderedList') ? 'is-active' : ''} aria-label="Ordered list">1.</button>
        <button type="button" onClick={() => editor.chain().focus().toggleCodeBlock().run()} className={editor.isActive('codeBlock') ? 'is-active' : ''} aria-label="Code block">{'</>'}</button>
        <button type="button" onClick={() => editor.chain().focus().toggleBlockquote().run()} className={editor.isActive('blockquote') ? 'is-active' : ''} aria-label="Quote">"</button>
        <span className="md-editor__sep" aria-hidden="true" />
        <button type="button" onClick={() => editor.commands.insertWikilink('New Note', null)} aria-label="Insert wikilink">[[ ]]</button>
      </div>

      <EditorContent editor={editor} className="md-editor__content" />

      {autocomplete.active && (
        <div className="md-editor__autocomplete" role="listbox" aria-label="Note suggestions">
          {autocomplete.items.length === 0 ? (
            <div className="md-editor__ac-empty">
              Press Enter to create "{autocomplete.query || 'New Note'}"
            </div>
          ) : (
            autocomplete.items.map((item) => (
              <div
                key={item}
                className="md-editor__ac-item"
                role="option"
                tabIndex={0}
                onMouseDown={(e) => { e.preventDefault(); insertWikilink(item); }}
              >
                {item}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
