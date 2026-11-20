// Agent text (plans, brainstorming questions, agent output) is Markdown: render it with GFM
// (tables, strikethrough, task lists). Raw HTML in the text is not rendered (react-markdown escapes
// it by default), and links are shown, not followed: the webview must not navigate away.
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  a: ({ children, href }) => <span className="md-link" title={href}>{children}</span>,
  table: ({ children }) => (
    <div className="md-table">
      <table>{children}</table>
    </div>
  ),
};

export function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className ? `md ${className}` : "md"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
