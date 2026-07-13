import { getAgent } from "@/lib/agent";

export const runtime = "nodejs";

export async function GET() {
  return Response.json(getAgent().memoryStats());
}
