import { TranslationView } from "@/components/translation";
import { RequireAuth } from "@/components/shell";
import { VIEWER_ROUTE_IDS } from "@/data/routeParams";

export function generateStaticParams() {
  return VIEWER_ROUTE_IDS.map((id) => ({ id }));
}

export default function TranslatedDocumentPage() {
  return (
    <RequireAuth>
      <TranslationView />
    </RequireAuth>
  );
}
