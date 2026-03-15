import { NextResponse } from 'next/server';

export async function GET() {
  const coordinatorBaseUrl =
    process.env.COORDINATOR_HTTP_BASE_URL ||
    process.env.NEXT_PUBLIC_COORDINATOR_HTTP ||
    'http://127.0.0.1:8000';

  try {
    const response = await fetch(`${coordinatorBaseUrl}/status`, {
      method: 'GET',
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
        error: 'Failed to reach coordinator /status endpoint',
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 502 }
    );
  }
}
