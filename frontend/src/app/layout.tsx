import type { Metadata } from "next";
import Image from "next/image";
import localFont from "next/font/local";
import "./globals.css";

const inter = localFont({
  src: "../assets/fonts/InterVariable.woff2",
  variable: "--font-inter",
  display: "swap",
  preload: false,
  weight: "100 900",
  style: "normal",
});

const jetbrainsMono = localFont({
  src: "../assets/fonts/JetBrainsMonoVariable.woff2",
  variable: "--font-jetbrains-mono",
  display: "swap",
  preload: false,
  weight: "100 800",
  style: "normal",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://justippo.tech"),
  title: "Justippo is being reworked",
  description: "A new Justippo is taking shape. We’ll be back soon.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  void children;

  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen antialiased">
        <main
          aria-labelledby="maintenance-title"
          style={{
            minHeight: "100svh",
            display: "grid",
            placeItems: "center",
            padding: "clamp(1.25rem, 5vw, 4rem)",
            background: "#f5efdf",
            color: "#17304a",
            textAlign: "center",
          }}
        >
          <section style={{ width: "min(100%, 38rem)", display: "grid", justifyItems: "center", gap: "1rem" }}>
            <p
              style={{
                margin: 0,
                fontFamily: "var(--font-jetbrains-mono), ui-monospace, monospace",
                fontSize: "0.75rem",
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "#53726e",
              }}
            >
              Justippo · cross-border documents
            </p>
            <h1
              id="maintenance-title"
              style={{
                margin: 0,
                fontFamily: "var(--font-inter), system-ui, sans-serif",
                fontSize: "clamp(1.7rem, 4vw, 2.5rem)",
                lineHeight: 1.15,
                fontWeight: 700,
                letterSpacing: "-0.04em",
              }}
            >
              We’re reworking Justippo.
            </h1>
            <p style={{ maxWidth: "31rem", margin: 0, fontSize: "1rem", lineHeight: 1.65, color: "#52616a" }}>
              A clearer way to search, translate, and share cross-border documents is taking shape.
            </p>
            <Image
              src="/justippo-wip-sticker.png"
              alt="Retro compass-and-document sticker reading Work in Progress"
              width={1024}
              height={1024}
              priority
              sizes="(max-width: 640px) 88vw, 34rem"
              style={{ width: "min(88vw, 34rem)", height: "auto", marginTop: "0.5rem" }}
            />
            <p style={{ margin: 0, fontSize: "0.875rem", color: "#61736f" }}>
              Thanks for your patience.
            </p>
          </section>
        </main>
      </body>
    </html>
  );
}
