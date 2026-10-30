/**
 * Eurostat JSON-stat parser — maps positional integer keys to country codes.
 *
 * The Eurostat Statistics API returns JSON-stat 2.0 format, NOT SDMX-JSON.
 * The `value` object uses positional integer keys (e.g. "0", "1", "2"...)
 * that map to dimension categories via `dimension.<name>.category.index`.
 *
 * For a multi-geo query (geo=DE,FR,IT...), the flat index is computed from
 * the Cartesian product of all dimension sizes. The geo dimension's stride
 * depends on its position in the `id` array.
 */

export interface EurostatResponse {
  readonly id: readonly string[];
  readonly size: readonly number[];
  readonly dimension: {
    readonly [key: string]: {
      readonly category: {
        readonly index: { readonly [code: string]: number };
        readonly label: { readonly [code: string]: string };
      };
    };
  };
  readonly value: { readonly [key: string]: number | null };
}

export interface CountryStat {
  readonly code: string;
  readonly label: string;
  readonly count: number;
}

export interface MigrationStats {
  readonly total: number;
  readonly countries: readonly CountryStat[];
  readonly year: string;
  readonly source: string;
}

const EUROSTAT_DATASET_URL =
  "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/migr_pop1ctz";

const COUNTRY_FLAG_EMOJI: Readonly<Record<string, string>> = {
  DE: "🇩🇪",
  FR: "🇫🇷",
  IT: "🇮🇹",
  ES: "🇪🇸",
  NL: "🇳🇱",
  AT: "🇦🇹",
  BE: "🇧🇪",
  PL: "🇵🇱",
  SE: "🇸🇪",
  EL: "🇬🇷",
  EU27_2020: "🇪🇺",
};

const LANGUAGE_SUGGESTION: Readonly<Record<string, string>> = {
  DE: "de",
  FR: "fr",
};

function getCountryFlag(code: string): string {
  return COUNTRY_FLAG_EMOJI[code] ?? "🏳️";
}

function getLanguageSuggestion(code: string): string {
  return LANGUAGE_SUGGESTION[code] ?? "en";
}

function computeFlatIndex(indices: readonly number[], sizes: readonly number[]): number {
  let flat = 0;
  let stride = 1;
  for (let i = indices.length - 1; i >= 0; i--) {
    flat += indices[i] * stride;
    stride *= sizes[i];
  }
  return flat;
}

export function parseEurostatResponse(data: EurostatResponse): MigrationStats {
  const id = data.id;
  const size = data.size;
  const value = data.value;

  const geoDim = data.dimension.geo;
  if (!geoDim) {
    return { total: 0, countries: [], year: "", source: "Eurostat" };
  }

  const geoIndex = geoDim.category.index;
  const geoLabel = geoDim.category.label;
  const geoPosition = id.indexOf("geo");
  const timePosition = id.indexOf("time");

  const countries: CountryStat[] = [];
  let total = 0;

  for (const [code, pos] of Object.entries(geoIndex)) {
    // Build the index array for this geo code
    const indices: number[] = new Array(id.length).fill(0);
    indices[geoPosition] = pos;
    // All other dimensions use index 0 (we filtered to single values)
    const flatKey = String(computeFlatIndex(indices, size));
    const rawValue = value[flatKey];

    if (rawValue === null || rawValue === undefined) {
      continue;
    }

    const count = typeof rawValue === "number" ? rawValue : 0;
    const label = geoLabel[code] ?? code;

    if (code === "EU27_2020") {
      total = count;
    } else {
      countries.push({ code, label, count });
    }
  }

  countries.sort((a, b) => b.count - a.count);

  let year = "";
  if (timePosition >= 0) {
    const timeDim = data.dimension.time;
    if (timeDim) {
      const timeCodes = Object.keys(timeDim.category.index);
      if (timeCodes.length > 0) {
        year = timeCodes[0];
      }
    }
  }

  return {
    total,
    countries: countries.slice(0, 5),
    year,
    source: "Eurostat, migr_pop1ctz",
  };
}

export function getCountryFlagEmoji(code: string): string {
  return getCountryFlag(code);
}

export function getLanguageSuggestionForCountry(code: string): string {
  return getLanguageSuggestion(code);
}

export { EUROSTAT_DATASET_URL };
