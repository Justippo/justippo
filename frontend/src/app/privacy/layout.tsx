import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — EvidenceEU",
  description: "Privacy and data protection policy for EvidenceEU.",
};

export default function PrivacyLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
