import { useEffect, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, highlightActiveLine } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { HighlightStyle, syntaxHighlighting, indentUnit, bracketMatching } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";

// Colours from the mockup's code panel.
const highlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.definitionKeyword, t.operatorKeyword], color: "#F59E6B" },
  { tag: [t.string, t.special(t.string)], color: "#F2D28B" },
  { tag: [t.number, t.bool, t.null], color: "#8FC7FF" },
  { tag: [t.comment, t.lineComment, t.docComment], color: "#8A8F9C" },
  { tag: [t.function(t.definition(t.variableName)), t.definition(t.className)], color: "#9EE6C9" },
]);

const theme = EditorView.theme(
  {
    "&": { backgroundColor: "#15171C", color: "#E4E5E9", fontSize: "13px", height: "100%" },
    ".cm-content": { fontFamily: "'JetBrains Mono', monospace", lineHeight: "1.65", padding: "16px 0", caretColor: "#F59E5B" },
    ".cm-gutters": { backgroundColor: "#15171C", color: "#5B5F6A", border: "none" },
    ".cm-activeLine": { backgroundColor: "#1C1F26" },
    ".cm-activeLineGutter": { backgroundColor: "#1C1F26" },
    "&.cm-focused .cm-cursor": { borderLeftColor: "#F59E5B" },
    "&.cm-focused .cm-selectionBackground, ::selection": { backgroundColor: "#2F3A55" },
    ".cm-scroller": { fontFamily: "'JetBrains Mono', monospace" },
  },
  { dark: true },
);

export function CodeEditor({ path, value, onChange }: { path: string; value: string; onChange: (v: string) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const change = useRef(onChange);
  change.current = onChange;

  useEffect(() => {
    if (!host.current) return;
    const extensions = [
      lineNumbers(),
      history(),
      highlightActiveLine(),
      bracketMatching(),
      indentUnit.of("    "),
      keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
      syntaxHighlighting(highlight),
      theme,
      EditorView.lineWrapping,
      EditorView.updateListener.of((u) => {
        if (u.docChanged) change.current(u.state.doc.toString());
      }),
      EditorView.contentAttributes.of({ "aria-label": `Editor: ${path}` }),
    ];
    if (path.endsWith(".py")) extensions.push(python());
    view.current = new EditorView({ state: EditorState.create({ doc: value, extensions }), parent: host.current });
    return () => view.current?.destroy();
    // A new file gets a new editor; value changes from outside are not pushed back in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  return <div className="code-host" ref={host} />;
}
