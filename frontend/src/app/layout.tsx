import type { Metadata } from "next";
import { Inter, Geist } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});


// =============================================================================
// Fonts
// =============================================================================
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

// =============================================================================
// Metadata (SEO)
// =============================================================================
export const metadata: Metadata = {
  title: {
    default: "Enterprise RAG AI Assistant",
    template: "%s | Enterprise RAG AI Assistant",
  },
  description:
    "A production-ready Enterprise Retrieval-Augmented Generation AI Assistant — " +
    "upload your documents and get instant, grounded answers.",
  keywords: [
    "RAG",
    "AI",
    "enterprise",
    "document Q&A",
    "LLM",
    "FastAPI",
    "Next.js",
  ],
  authors: [{ name: "Engineering Team" }],
  openGraph: {
    type: "website",
    locale: "en_US",
    title: "Enterprise RAG AI Assistant",
    description: "Production-ready Enterprise RAG AI Assistant",
    siteName: "Enterprise RAG AI Assistant",
  },
  robots: {
    index: true,
    follow: true,
  },
};

// =============================================================================
// Root Layout
// =============================================================================
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={cn("dark", inter.variable, "font-sans", geist.variable)} suppressHydrationWarning>
      <body className="font-sans antialiased bg-background text-foreground">
        {children}
      </body>
    </html>
  );
}
