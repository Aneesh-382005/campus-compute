import { NextResponse } from 'next/server';

export async function POST(req) {
  const body = await req.json();
  console.log('[submit-job] received', body);
  return NextResponse.json({ status: 'ok', received: body });
}
