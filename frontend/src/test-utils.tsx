import { type ReactElement, type ReactNode } from "react";
import { render, type RenderOptions, RenderResult } from "@testing-library/react";
import { TolgeeProvider } from "@tolgee/react";
import { staticData } from "@/lib/tolgee";
import { Tolgee, FormatSimple } from "@tolgee/web";

// Create a Tolgee instance for testing
const mockTolgee = Tolgee()
  .use(FormatSimple())
  .init({
    defaultLanguage: "en",
    availableLanguages: ["en", "de", "fr"],
    fallbackLanguage: "en",
    staticData,
  });

// Initialize Tolgee synchronously for tests
void mockTolgee.run();

// Provider with real Tolgee for tests that need it
function TestTolgeeProvider({ children }: { readonly children: ReactNode }) {
  return (
    <TolgeeProvider tolgee={mockTolgee} fallback="">
      {children}
    </TolgeeProvider>
  );
}

// Simple mock provider for tests that don't need Tolgee
function TestProvider({ children }: { readonly children: ReactNode }) {
  return <>{children}</>;
}

// Custom render function that wraps with simple provider (for tests not using useT)
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">
): RenderResult {
  return render(ui, { wrapper: TestProvider, ...options });
}

// Custom render function that wraps with Tolgee provider (for tests using useT)
export function renderWithI18n(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">
): RenderResult {
  return render(ui, { wrapper: TestTolgeeProvider, ...options });
}

export { TestTolgeeProvider as TestI18nProvider };

// Export mockT for direct use in tests if needed
export function mockT(key: string, params?: Record<string, string | number>): string {
  if (params) {
    return Object.entries(params).reduce((str, [k, v]) => {
      const regex = new RegExp("\\{" + k + "\\}", "g");
      return str.replace(regex, String(v));
    }, key);
  }
  return key;
}
