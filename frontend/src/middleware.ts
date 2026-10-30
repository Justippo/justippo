// SPDX-License-Identifier: MIT
/**
 * Edge Middleware — No Node.js APIs (Cloudflare Pages safe).
 *
 * 1. Locale detection (NEXT_LOCALE cookie → Accept-Language → "en").
 * 2. Auth-aware redirect: authenticated users on "/" → "/dashboard".
 *
 * Auth is detected via a client-set cookie (evidenceeu_auth_token) written by
 * the auth context on login/session-confirm. This avoids a network round-trip.
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const SUPPORTED = ["en", "de", "fr"] as const;
const DEFAULT_LOCALE = "en";
const AUTH_COOKIE_NAME = "evidenceeu_auth_token";

function detectLocale(req: NextRequest): string {
  const cookieLocale = req.cookies.get("NEXT_LOCALE")?.value;
  if (cookieLocale && (SUPPORTED as readonly string[]).includes(cookieLocale)) {
    return cookieLocale;
  }
  const acceptLang = req.headers.get("accept-language") ?? "";
  for (const part of acceptLang.split(",")) {
    const tag = part.split(";")[0].trim().split("-")[0].toLowerCase();
    if ((SUPPORTED as readonly string[]).includes(tag)) return tag;
  }
  return DEFAULT_LOCALE;
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const authCookie = req.cookies.get(AUTH_COOKIE_NAME)?.value;
  if (authCookie === "true" && pathname === "/") {
    const url = req.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  const locale = detectLocale(req);
  const res = NextResponse.next();
  res.headers.set("x-locale", locale);
  return res;
}

export const config = {
  matcher: ["/((?!_next|favicon.ico|apple-touch-icon.png|favicon.png).*)"],
};
