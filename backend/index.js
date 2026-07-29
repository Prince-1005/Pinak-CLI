const express = require('express');
const cors = require('cors');
const crypto = require('crypto');
const { createClient } = require('@supabase/supabase-js');
const { Ratelimit } = require('@upstash/ratelimit');
const { Redis } = require('@upstash/redis');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

// Initialize Supabase Admin Client
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co';
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || 'placeholder';
const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey);

// Initialize Upstash Redis for rate limiting
let ratelimit = null;
const redisUrl = process.env.UPSTASH_REDIS_REST_URL;
const redisToken = process.env.UPSTASH_REDIS_REST_TOKEN;
if (redisUrl && redisToken) {
  ratelimit = new Ratelimit({
    redis: new Redis({ url: redisUrl, token: redisToken }),
    limiter: Ratelimit.slidingWindow(30, '1 m'), // 30 events per minute per IP
  });
}

// UptimeRobot keep-awake ping route
app.get('/ping', (req, res) => {
  res.status(200).json({ status: 'alive', message: 'PINAK Backend is active' });
});

// Activity tracking endpoint for PINAK CLI
app.post('/api/v1/track', async (req, res) => {
  try {
    // 1. Rate Limiting
    if (ratelimit) {
      const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress || '127.0.0.1';
      const { success } = await ratelimit.limit(ip);
      if (!success) {
        return res.status(429).json({ error: 'Too Many Requests' });
      }
    }

    const body = req.body;
    const {
      activity_type,
      username,
      device_id,
      command,
      url,
      status,
      mode,
      duration,
      size,
      session_id,
      platform,
    } = body;

    // 2. Validate required fields
    const validActivityTypes = ['session_start', 'session_end', 'download', 'command'];
    if (!activity_type || !validActivityTypes.includes(activity_type)) {
      return res.status(400).json({
        error: `Invalid or missing activity_type. Must be one of: ${validActivityTypes.join(', ')}`
      });
    }

    if (!device_id) {
      return res.status(400).json({ error: 'Missing required field: device_id' });
    }

    // 3. HMAC Signature Verification (optional - skipped if PINAK_HMAC_SECRET not set)
    const timestamp = req.headers['x-pinak-timestamp'];
    const signature = req.headers['x-pinak-signature'];
    const secret = process.env.PINAK_HMAC_SECRET;

    if (secret && signature && timestamp) {
      const now = Math.floor(Date.now() / 1000);
      if (Math.abs(now - parseInt(timestamp, 10)) > 300) {
        return res.status(401).json({ error: 'Request expired (timestamp out of tolerance).' });
      }

      const expectedSignature = crypto
        .createHmac('sha256', secret)
        .update(`${timestamp}.${JSON.stringify(body)}`)
        .digest('hex');

      if (signature !== expectedSignature) {
        return res.status(401).json({ error: 'Invalid HMAC signature.' });
      }
    }

    // 4. Save to Supabase
    const { error: dbError } = await supabaseAdmin.from('activity_logs').insert([
      {
        activity_type: activity_type,
        username: (username || 'anonymous').substring(0, 120),
        device_id: String(device_id).substring(0, 128),
        command: command ? String(command).substring(0, 1024) : null,
        url: url ? String(url).substring(0, 2048) : null,
        status: status ? String(status).substring(0, 32) : null,
        mode: mode ? String(mode).substring(0, 16) : null,
        duration: Number(duration) || 0,
        size: Number(size) || 0,
        session_id: session_id ? String(session_id).substring(0, 64) : null,
        platform: (platform || 'unknown').substring(0, 64),
      },
    ]);

    if (dbError) {
      console.error('Database Error:', dbError);
      return res.status(500).json({ error: 'Failed to record activity to database.' });
    }

    return res.status(200).json({
      success: true,
      message: `Activity "${activity_type}" recorded successfully.`,
      timestamp: new Date().toISOString(),
    });

  } catch (err) {
    console.error('API Error:', err);
    return res.status(500).json({ error: 'Internal Server Error' });
  }
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`PINAK Backend running on port ${PORT}`);
});
