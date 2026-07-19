/**
 * Enterprise RAG AI Assistant — Homepage
 * =======================================
 * Server-rendered parent that exports static SEO metadata and mounts
 * the client-side interactive HomeClient dashboard component.
 */

import type { Metadata } from "next";
import HomeClient from "./HomeClient";

// =============================================================================
// Metadata (SEO)
// =============================================================================
export const metadata: Metadata = {
  title: "Home",
  description:
    "Enterprise RAG AI Assistant — upload documents and get instant, grounded AI answers.",
};

export default function HomePage() {
  return <HomeClient />;
}
