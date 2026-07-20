import { NextRequest, NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/supabase';
import crypto from 'crypto';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { user_name, command_executed, target_link, cli_version } = body;

    // Validate required fields
    if (!user_name || !command_executed || !target_link) {
      return NextResponse.json(
        { error: 'Missing required fields: user_name, command_executed, and target_link are required.' },
        { status: 400 }
      );
    }

    // Optional HMAC Signature Verification
    const timestamp = req.headers.get('x-pinak-timestamp');
    const signature = req.headers.get('x-pinak-signature');
    const secret = process.env.PINAK_HMAC_SECRET;

    if (secret && signature && timestamp) {
      // Replay attack prevention (5 minute window)
      const now = Math.floor(Date.now() / 1000);
      if (Math.abs(now - parseInt(timestamp, 10)) > 300) {
        return NextResponse.json({ error: 'Request expired (timestamp out of tolerance).' }, { status: 401 });
      }

      // Compute expected HMAC signature
      const expectedSignature = crypto
        .createHmac('sha256', secret)
        .update(`${timestamp}.${JSON.stringify(body)}`)
        .digest('hex');

      if (signature !== expectedSignature) {
        return NextResponse.json({ error: 'Invalid HMAC signature.' }, { status: 401 });
      }
    }

    // Extract & hash IP address for privacy compliance
    const rawIp = req.headers.get('x-forwarded-for') || req.ip || '127.0.0.1';
    const ipHash = crypto.createHash('sha256').update(rawIp + 'PINAK_SALT').digest('hex').substring(0, 16);

    // Save log entry to Supabase
    const { data, error } = await supabaseAdmin.from('download_command_logs').insert([
      {
        user_name,
        command_executed,
        target_link,
        cli_version: cli_version || '1.0.0',
        ip_hash: ipHash,
        status: 'SUCCESS',
      },
    ]);

    if (error) {
      console.error('Database Error:', error);
      return NextResponse.json({ error: 'Failed to record log to database.' }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      message: 'Download command log recorded successfully.',
      timestamp: new Date().toISOString(),
    });
  } catch (err: any) {
    console.error('API Error:', err);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
