import { LegacyWorkflowRedirect } from "@/components/translation";
import { COMPARE_ROUTE_IDS } from "@/data/routeParams";

export function generateStaticParams() {
  return COMPARE_ROUTE_IDS.map((id) => ({ id }));
}

export default function CompareDocumentPage() {
  return <LegacyWorkflowRedirect destination="/translation?view=compare" />;
}
