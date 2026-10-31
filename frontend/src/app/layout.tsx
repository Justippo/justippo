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
  title: "Justippo · Work in progress",
  description: "Justippo is being rebuilt. A refreshed experience is on its way.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  void children;

  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen antialiased">
        <main
          aria-labelledby="maintenance-message"
          style={{
            minHeight: "100svh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "clamp(0.75rem, 2.5vh, 1.5rem)",
            padding: "1.25rem",
            background: "#ffffff",
            color: "#17304a",
            textAlign: "center",
          }}
        >
          <Image
            src="/justippo-wip-sticker-transparent.png"
            alt="Retro compass-and-document sticker reading Work in Progress"
            width={1024}
            height={1024}
            priority
            sizes="(max-width: 640px) 88vw, 34rem"
            style={{ width: "min(88vw, 34rem)", height: "auto" }}
          />
          <p
            id="maintenance-message"
            style={{
              maxWidth: "100%",
              margin: 0,
              whiteSpace: "nowrap",
              fontFamily: "Georgia, 'Times New Roman', serif",
              fontSize: "clamp(0.62rem, 2.2vw, 0.78rem)",
              fontVariant: "small-caps",
              letterSpacing: "0.12em",
              lineHeight: 1.5,
              color: "#52616a",
            }}
          >
            Justippo is under reconstruction
          </p>
        </main>
      </body>
    </html>
  );
}
