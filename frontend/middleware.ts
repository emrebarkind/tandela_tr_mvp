import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const username = process.env.PREVIEW_BASIC_AUTH_USER;
  const password = process.env.PREVIEW_BASIC_AUTH_PASSWORD;
  if (!username || !password) return NextResponse.next();

  const authorization = request.headers.get("authorization");
  if (authorization?.startsWith("Basic ")) {
    const decoded = atob(authorization.slice(6));
    if (decoded === `${username}:${password}`) return NextResponse.next();
  }

  return new NextResponse("Kimlik doğrulama gerekli.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Tandela Preview"' },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
