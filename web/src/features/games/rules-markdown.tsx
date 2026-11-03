import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

// Headings drop one level so the page title stays the only h1.
const COMPONENTS: Components = {
  h1: ({ children }) => <h2 className="mt-2 mb-3 text-xl font-semibold tracking-tight">{children}</h2>,
  h2: ({ children }) => <h3 className="mt-6 mb-2 text-lg font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-4 mb-2 font-semibold">{children}</h4>,
  h4: ({ children }) => <h5 className="mt-3 mb-1 font-medium">{children}</h5>,
  p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="my-2 ml-5 list-disc space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 ml-5 list-decimal space-y-1">{children}</ol>,
  code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{children}</code>,
  pre: ({ children }) => <pre className="my-3 overflow-x-auto rounded-lg bg-muted p-3 text-xs [&_code]:bg-transparent [&_code]:p-0">{children}</pre>,
  table: ({ children }) => <Table className="my-3">{children}</Table>,
  thead: ({ children }) => <TableHeader>{children}</TableHeader>,
  tbody: ({ children }) => <TableBody>{children}</TableBody>,
  tr: ({ children }) => <TableRow>{children}</TableRow>,
  th: ({ children }) => <TableHead>{children}</TableHead>,
  td: ({ children }) => <TableCell className="whitespace-normal">{children}</TableCell>,
};

/** A game's rules.md, with GitHub tables. */
export function RulesMarkdown({ text }: { text: string }) {
  return (
    <div className="text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
