import { Suspense } from "react";
import { CitationAccessView } from "@/components/citation";

export default function CitationPage() {
  return (
    <Suspense fallback={null}>
      <CitationAccessView />
    </Suspense>
  );
}
