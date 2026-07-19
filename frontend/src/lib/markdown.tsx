import React from "react";

/**
 * Custom React-based Markdown rendering engine that parses:
 * - Paragraphs
 * - Lists (ordered and unordered)
 * - Tables (collapsible and styled SaaS headers)
 * - Code blocks (syntax styling)
 * - Bold/Italic formatting
 * - Bracketed citations [1] (triggers smooth scroll triggers back to grounding files)
 */
export function renderMarkdown(
  text: string,
  onCitationClick?: (idx: number) => void
): React.ReactNode {
  if (!text) return null;

  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];

  let inCodeBlock = false;
  let codeBlockLines: string[] = [];
  let codeBlockLang = "";

  let inTable = false;
  let tableHeader: string[] = [];
  let tableRows: string[][] = [];

  let inList = false;
  let listItems: React.ReactNode[] = [];
  let listType: "ul" | "ol" = "ul";

  const flushCodeBlock = (key: string | number) => {
    if (codeBlockLines.length > 0) {
      elements.push(
        <pre
          key={`code-${key}`}
          className="bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-xs overflow-x-auto text-indigo-300 my-4 shadow-inner"
        >
          {codeBlockLang && (
            <div className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-2 border-b border-slate-950 pb-1">
              {codeBlockLang}
            </div>
          )}
          <code>{codeBlockLines.join("\n")}</code>
        </pre>
      );
      codeBlockLines = [];
      codeBlockLang = "";
    }
  };

  const flushTable = (key: string | number) => {
    if (tableHeader.length > 0 || tableRows.length > 0) {
      elements.push(
        <div
          key={`table-${key}`}
          className="overflow-x-auto my-4 rounded-xl border border-slate-850 bg-slate-900/10 backdrop-blur-sm"
        >
          <table className="min-w-full divide-y divide-slate-800 text-xs text-left">
            {tableHeader.length > 0 && (
              <thead className="bg-slate-900/50 text-slate-400 font-bold uppercase tracking-wider">
                <tr>
                  {tableHeader.map((h, i) => (
                    <th key={i} className="px-4 py-2.5 font-semibold text-slate-300">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody className="divide-y divide-slate-850 bg-transparent text-slate-300">
              {tableRows.map((row, idx) => (
                <tr key={idx} className="hover:bg-slate-900/20 transition-colors">
                  {row.map((cell, i) => (
                    <td key={i} className="px-4 py-2.5 font-medium">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableHeader = [];
      tableRows = [];
    }
  };

  const flushList = (key: string | number) => {
    if (listItems.length > 0) {
      const ListTag = listType;
      elements.push(
        <ListTag
          key={`list-${key}`}
          className={`${
            listType === "ul" ? "list-disc" : "list-decimal"
          } pl-6 my-3.5 space-y-1.5 text-xs md:text-sm text-slate-200`}
        >
          {listItems}
        </ListTag>
      );
      listItems = [];
    }
  };

  const parseInlineStyles = (segment: string, keyPrefix: string): React.ReactNode[] => {
    const parts = segment.split(/(\[\d+\])/g);

    return parts.map((part, idx) => {
      const citeMatch = part.match(/^\[(\d+)\]$/);
      if (citeMatch && onCitationClick) {
        const citeIdx = parseInt(citeMatch[1]);
        return (
          <span
            key={`${keyPrefix}-${idx}-cite`}
            onClick={() => onCitationClick(citeIdx)}
            className="mx-0.5 inline-flex items-center justify-center px-1.5 py-0.5 text-[9px] font-mono font-bold bg-indigo-500/20 hover:bg-indigo-500/35 text-indigo-300 border border-indigo-500/30 rounded cursor-pointer transition-all duration-150 select-none transform hover:scale-105 active:scale-95"
            title={`Jump to Source [${citeIdx}]`}
          >
            [{citeIdx}]
          </span>
        );
      }

      const inlineParts = part.split(/(\*\*.*?\*\*|\*.*?\*|`.*?`)/g);
      return (
        <span key={`${keyPrefix}-${idx}`}>
          {inlineParts.map((subPart, subIdx) => {
            if (subPart.startsWith("**") && subPart.endsWith("**")) {
              return (
                <strong key={subIdx} className="font-bold text-white">
                  {subPart.slice(2, -2)}
                </strong>
              );
            }
            if (subPart.startsWith("*") && subPart.endsWith("*")) {
              return (
                <em key={subIdx} className="italic text-slate-300">
                  {subPart.slice(1, -1)}
                </em>
              );
            }
            if (subPart.startsWith("`") && subPart.endsWith("`")) {
              return (
                <code
                  key={subIdx}
                  className="bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded text-indigo-400 font-mono text-[10px]"
                >
                  {subPart.slice(1, -1)}
                </code>
              );
            }
            return subPart;
          })}
        </span>
      );
    });
  };

  let elementKey = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. Code block boundary
    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        flushCodeBlock(elementKey++);
        inCodeBlock = false;
      } else {
        flushTable(elementKey++);
        flushList(elementKey++);
        inCodeBlock = true;
        codeBlockLang = trimmed.slice(3).trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(line);
      continue;
    }

    // 2. Table boundary
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      flushList(elementKey++);
      inTable = true;
      const cells = line
        .split("|")
        .slice(1, -1)
        .map((c) => c.trim());

      if (cells.every((c) => c.match(/^:?-+:?$/))) {
        continue;
      }

      if (tableHeader.length === 0) {
        tableHeader = cells;
      } else {
        tableRows.push(cells);
      }
      continue;
    } else if (inTable) {
      flushTable(elementKey++);
      inTable = false;
    }

    // 3. List boundary
    const unorderedMatch = line.match(/^(\s*)(?:-|\*|\+)\s+(.+)$/);
    const orderedMatch = line.match(/^(\s*)\d+\.\s+(.+)$/);

    if (unorderedMatch || orderedMatch) {
      flushTable(elementKey++);
      const isOrdered = !!orderedMatch;
      const content = isOrdered ? orderedMatch![2] : unorderedMatch![2];

      if (!inList) {
        inList = true;
        listType = isOrdered ? "ol" : "ul";
      } else if (isOrdered && listType !== "ol") {
        flushList(elementKey++);
        listType = "ol";
        inList = true;
      } else if (!isOrdered && listType !== "ul") {
        flushList(elementKey++);
        listType = "ul";
        inList = true;
      }

      listItems.push(
        <li key={listItems.length} className="leading-relaxed">
          {parseInlineStyles(content, `list-${elementKey}-${listItems.length}`)}
        </li>
      );
      continue;
    } else if (inList) {
      flushList(elementKey++);
      inList = false;
    }

    // 4. Paragraph text
    if (trimmed) {
      elements.push(
        <p
          key={elementKey++}
          className="text-xs md:text-sm leading-relaxed text-slate-300 my-2.5 font-sans"
        >
          {parseInlineStyles(line, `p-${elementKey}`)}
        </p>
      );
    }
  }

  // Final flush loops
  flushCodeBlock(elementKey++);
  flushTable(elementKey++);
  flushList(elementKey++);

  return <div className="space-y-1">{elements}</div>;
}
