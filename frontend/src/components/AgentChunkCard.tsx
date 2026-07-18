"use client";

/**
 * Enterprise RAG AI Assistant — Agent Chunk Card
 * ================================================
 * Displays a retrieved document chunk with score, metadata, and text preview.
 */

interface AgentChunkCardProps {
  chunkId?: string;
  documentId?: string;
  documentName: string;
  pageNumber?: number | null;
  sectionTitle?: string | null;
  text: string;
  score?: number;
  language?: string;
  chunkIndex?: number;
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    score >= 0.8
      ? "#6ee7b7"
      : score >= 0.6
      ? "#fcd34d"
      : "#fca5a5";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
      }}
    >
      <div
        style={{
          width: "36px",
          height: "36px",
          borderRadius: "50%",
          background: `conic-gradient(${color} ${pct}%, rgba(255,255,255,0.08) ${pct}%)`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
        }}
      >
        <div
          style={{
            width: "28px",
            height: "28px",
            borderRadius: "50%",
            background: "#1a1b2e",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color,
            }}
          >
            {pct}%
          </span>
        </div>
      </div>
    </div>
  );
}

export default function AgentChunkCard({
  documentName,
  pageNumber,
  sectionTitle,
  text,
  score,
  language,
  chunkIndex,
}: AgentChunkCardProps) {
  const preview = text.length > 280 ? text.slice(0, 280).trim() + "…" : text;

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.09)",
        borderRadius: "12px",
        padding: "14px 16px",
        transition: "border-color 0.2s ease, background 0.2s ease",
        cursor: "default",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor =
          "rgba(99,102,241,0.4)";
        (e.currentTarget as HTMLDivElement).style.background =
          "rgba(99,102,241,0.06)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor =
          "rgba(255,255,255,0.09)";
        (e.currentTarget as HTMLDivElement).style.background =
          "rgba(255,255,255,0.04)";
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "12px",
          marginBottom: "10px",
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              marginBottom: "4px",
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontSize: "13px" }}>📄</span>
            <span
              style={{
                fontSize: "13px",
                fontWeight: 600,
                color: "#e2e8f0",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: "200px",
              }}
              title={documentName}
            >
              {documentName}
            </span>
          </div>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "6px",
            }}
          >
            {pageNumber != null && (
              <span
                style={{
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.5)",
                  background: "rgba(255,255,255,0.06)",
                  padding: "2px 7px",
                  borderRadius: "4px",
                }}
              >
                p. {pageNumber}
              </span>
            )}
            {sectionTitle && (
              <span
                style={{
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.5)",
                  background: "rgba(255,255,255,0.06)",
                  padding: "2px 7px",
                  borderRadius: "4px",
                  maxWidth: "150px",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={sectionTitle}
              >
                §&nbsp;{sectionTitle}
              </span>
            )}
            {language && language !== "und" && (
              <span
                style={{
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.35)",
                  padding: "2px 7px",
                  background: "rgba(255,255,255,0.04)",
                  borderRadius: "4px",
                }}
              >
                {language.toUpperCase()}
              </span>
            )}
            {chunkIndex !== undefined && (
              <span
                style={{
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.3)",
                  padding: "2px 7px",
                  borderRadius: "4px",
                }}
              >
                chunk #{chunkIndex}
              </span>
            )}
          </div>
        </div>

        {score !== undefined && <ScoreBadge score={score} />}
      </div>

      {/* Text Preview */}
      <p
        style={{
          fontSize: "13px",
          color: "rgba(255,255,255,0.65)",
          lineHeight: 1.7,
          margin: 0,
          fontFamily: "'Inter', sans-serif",
        }}
      >
        {preview}
      </p>
    </div>
  );
}
