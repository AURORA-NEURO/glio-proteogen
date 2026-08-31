export const dynamic = "force-dynamic";

export function GET() {
  return Response.json(
    { status: "ok", service: "glio-proteogen-ui" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
