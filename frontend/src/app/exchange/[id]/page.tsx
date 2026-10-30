import { ExchangeView } from "@/components/exchange";
import { RequireAuth } from "@/components/shell";
import { EXCHANGE_ROUTE_IDS } from "@/data/routeParams";

export function generateStaticParams() {
  return EXCHANGE_ROUTE_IDS.map((id) => ({ id }));
}

export default function ExchangeRoomPage() {
  return (
    <RequireAuth>
      <ExchangeView />
    </RequireAuth>
  );
}
