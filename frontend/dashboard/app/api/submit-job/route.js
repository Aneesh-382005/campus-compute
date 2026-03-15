import { NextResponse } from 'next/server';

export async function POST(req) {
  const body = await req.json();
  const coordinatorBaseUrl =
    process.env.COORDINATOR_HTTP_BASE_URL ||
    process.env.NEXT_PUBLIC_COORDINATOR_HTTP ||
    'http://127.0.0.1:8000';

  try {
    const response = await fetch(`${coordinatorBaseUrl}/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    });

    const text = await response.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text };
    }

    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        error: 'Failed to reach coordinator /jobs endpoint',
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 502 }
    );
  }
}
