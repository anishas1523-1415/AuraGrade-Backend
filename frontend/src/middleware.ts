/**
 * AuraGrade — Next.js Middleware
 *
 * IMPORTANT: This file MUST be named middleware.ts (not proxy.ts)
 * and MUST export a function named `middleware` for Next.js to pick it up.
 * The previous src/proxy.ts exported `proxy` — which Next.js silently ignored,
 * meaning session refresh and auth redirects were never running.
 *
 * What this does:
 *  1. Refreshes the Supabase auth session cookie on every request (keeps tokens fresh)
 *  2. Redirects unauthenticated users to /login for protected routes
 *  3. Redirects already-logged-in users away from /login to /
 */
import { updateSession } from "@/lib/supabase/middleware";
import type { NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    /*
     * Match all request paths EXCEPT:
     * - _next/static  (Next.js static assets)
     * - _next/image   (Next.js image optimization)
     * - favicon.ico, sitemap.xml, robots.txt
     * - image files (svg, png, jpg, jpeg, gif, webp)
     *
     * This ensures the middleware runs on all page routes and API routes,
     * including /api/generate-rubric which needs the session for auth.
     */
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
