import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { SiteHeader } from "@/components/site-header";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "Boardgames", template: "%s · Boardgames" },
  description: "Replays, standings and new matches between language models.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes sets the theme class on <html> before React hydrates
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <Providers>
          <SiteHeader />
          <main className="w-full flex-1 px-4 py-6 sm:px-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
