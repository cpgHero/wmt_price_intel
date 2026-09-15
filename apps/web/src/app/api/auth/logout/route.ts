import { NextResponse } from "next/server";
import {
  ADMIN_ROUTE_CACHE_COOKIE_NAME,
  CUSTOMER_ROUTE_CACHE_COOKIE_NAME,
} from "../../../../lib/route-auth-cache";
import { publicRequestOrigin } from "../../../../lib/request-origin";

export const dynamic = "force-dynamic";

function expiredRouteCacheCookie(name: string): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${name}=; HttpOnly; Max-Age=0; Path=/; SameSite=Strict${secure}`;
}

export function GET(request: Request) {
  const url = new URL("/", publicRequestOrigin(request));
  const response = NextResponse.redirect(url);
  const headers = response.headers;
  headers.append(
    "set-cookie",
    expiredRouteCacheCookie(CUSTOMER_ROUTE_CACHE_COOKIE_NAME),
  );
  headers.append(
    "set-cookie",
    expiredRouteCacheCookie(ADMIN_ROUTE_CACHE_COOKIE_NAME),
  );
  return response;
}
