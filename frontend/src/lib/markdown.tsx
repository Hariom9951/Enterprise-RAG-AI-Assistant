import React from "react";

/**
 * Custom React-based Markdown rendering engine that parses:
 * - Paragraphs
 * - Lists (ordered and unordered)
 * - Tables (collapsible and styled SaaS headers)
 * - Code blocks (syntax styling)
 * - Bold/Italic formatting
 * - Bracketed citations [1] or (1) (triggers smooth scroll back to grounding files)
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
          className="bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-xs overflow-x-auto text-slate-100 my-3 shadow-xs"
        >
          {codeBlockLang && (
            <div className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider mb-2 border-b border-slate-800 pb-1">
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
          className="overflow-x-auto my-3 rounded-xl border border-slate-200 bg-white shadow-xs"
        >
          <table className="min-w-full divide-y divide-slate-200 text-xs text-left">
            {tableHeader.length > 0 && (
              <thead className="bg-slate-50 text-slate-600 font-semibold uppercase tracking-wider">
                <tr>
                  {tableHeader.map((h, i) => (
                    <th key={i} className="px-4 py-2.5 font-semibold text-slate-700">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
              {tableRows.map((row, idx) => (
                <tr key={idx} className="hover:bg-slate-50/60 transition-colors">
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
          } pl-5 my-2.5 space-y-1.5 text-xs md:text-sm text-slate-800`}
        >
          {listItems}
        </ListTag>
      );
      listItems = [];
    }
  };

  const parseInlineStyles = (segment: string, keyPrefix: string): React.ReactNode[] => {
    // Match either [1] or circled unicode digits like ① or (1)
    const parts = segment.split(/(\[\d+\]|\(\d+\))/g);

    return parts.map((part, idx) => {
      const citeMatch = part.match(/^\[(\d+)\]$/) || part.match(/^\((\d+)\)$/);
      if (citeMatch && onCitationClick) {
        const citeIdx = parseInt(citeMatch[1]);
        return (
          <button
            key={`${keyPrefix}-${idx}-cite`}
            type="button"
            onClick={() => onCitationClick(citeIdx)}
            className="inline-flex items-center justify-center w-4 h-4 mx-0.5 text-[10px] font-semibold text-blue-600 bg-blue-50 border border-blue-200 rounded-full hover:bg-blue-100 hover:scale-105 active:scale-95 transition-all cursor-pointer align-baseline select-none"
            title={`Jump to Source [${citeIdx}]`}
          >
            {citeIdx}
          </button>
        );
      }

      const inlineParts = part.split(/(\*\*.*?\*\*|\*.*?\*|`.*?`)/g);
      return (
        <span key={`${keyPrefix}-${idx}`}>
          {inlineParts.map((subPart, subIdx) => {
            if (subPart.startsWith("**") && subPart.endsWith("**")) {
              return (
                <strong key={subIdx} className="font-semibold text-slate-900">
                  {subPart.slice(2, -2)}
                </strong>
              );
            }
            if (subPart.startsWith("*") && subPart.endsWith("*")) {
              return (
                <em key={subIdx} className="italic text-slate-700">
                  {subPart.slice(1, -1)}
                </em>
              );
            }
            if (subPart.startsWith("`") && subPart.endsWith("`")) {
              return (
                <code
                  key={subIdx}
                  className="bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded text-slate-800 font-mono text-[11px]"
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
          className="text-xs md:text-sm leading-relaxed text-slate-800 my-2 font-normal"
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
