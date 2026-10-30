import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — EvidenceEU",
  description: "Terms and conditions for using EvidenceEU.",
};

export default function TermsLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
