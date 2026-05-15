import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "teammate — DevSecOps Brain",
  description: "Query your team's brain. Index past incidents. Run war-rooms.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-zinc-100 text-zinc-900 min-h-screen">
        <header className="bg-white border-b border-zinc-200 sticky top-0 z-50">
          <div className="max-w-screen-2xl mx-auto px-6 h-14 flex items-center justify-between">
            <div className="flex items-center gap-8">
              <div className="flex items-center gap-2 font-semibold">
                <span className="text-2xl">🧠</span>
                <span>teammate</span>
              </div>
              <nav className="flex items-center gap-1 text-sm">
                <Link href="/"        className="px-3 py-1.5 rounded-md hover:bg-zinc-100">Chat</Link>
                <Link href="/watch"   className="px-3 py-1.5 rounded-md hover:bg-zinc-100">Watch</Link>
                <Link href="/war"     className="px-3 py-1.5 rounded-md hover:bg-zinc-100">War</Link>
                <Link href="/feed"    className="px-3 py-1.5 rounded-md hover:bg-zinc-100">Feed</Link>
                <Link href="/index-status" className="px-3 py-1.5 rounded-md hover:bg-zinc-100">Index</Link>
                <Link href="/settings"     className="px-3 py-1.5 rounded-md hover:bg-zinc-100">Settings</Link>
              </nav>
            </div>
          </div>
        </header>
        <main className="max-w-screen-2xl mx-auto px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
