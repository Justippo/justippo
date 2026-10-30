import { useT } from "./useT";

interface PrimaryNavigationItem {
  readonly href: string;
  readonly label: string;
}

interface PrimaryNavigationDefinition {
  readonly href: string;
  readonly labelKey: string;
}

const PUBLIC_NAVIGATION_ITEMS: readonly PrimaryNavigationDefinition[] = [
  { href: "/search", labelKey: "nav.search" },
  { href: "/chat", labelKey: "nav.chat" },
  { href: "/translation", labelKey: "nav.translate" },
];

const AUTHENTICATED_NAVIGATION_ITEMS: readonly PrimaryNavigationDefinition[] = [
  { href: "/dashboard", labelKey: "nav.dashboard" },
  { href: "/exchange", labelKey: "nav.exchange" },
];

/** Returns the canonical primary navigation in its product-defined order. */
export function usePrimaryNavigation(isAuthenticated: boolean): readonly PrimaryNavigationItem[] {
  const { t } = useT();
  const items = isAuthenticated
    ? [...PUBLIC_NAVIGATION_ITEMS, ...AUTHENTICATED_NAVIGATION_ITEMS]
    : PUBLIC_NAVIGATION_ITEMS;

  return items.map(({ href, labelKey }) => ({
    href,
    label: t(labelKey),
  }));
}
