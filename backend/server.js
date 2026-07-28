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
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || '';
const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey);

// Initialize Upstash Redis for rate limiting
let ratelimit = null;
const redisUrl = process.env.UPSTASH_REDIS_REST_URL;
const redisToken = process.env.UPSTASH_REDIS_REST_TOKEN;
if (redisUrl && redisToken) {
  ratelimit = new Ratelimit({
    redis: new Redis({ url: redisUrl, token: redisToken }),
    limiter: Ratelimit.slidingWindow(10, '1 m'), // 10 requests per minute
  });
}

// Keep-awake ping route for UptimeRobot
app.get('/ping', (req, res) => {
  res.status(200).json({ status: 'alive', message: 'Backend is active' });
});

// Logging route for PINAK CLI
app.post('/api/v1/log-download', async (req, res) => {
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
    const { user_name, command_executed, target_link, cli_version } = body;

    // 2. Validate required fields
    if (!user_name || !command_executed || !target_link) {
      return res.status(400).json({ 
        error: 'Missing required fields: user_name, command_executed, and target_link are required.' 
      });
    }

    // 3. HMAC Signature Verification
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

    // 4. IP Hashing
    const rawIp = req.headers['x-forwarded-for'] || req.socket.remoteAddress || '127.0.0.1';
    const ipHash = crypto.createHash('sha256').update(rawIp + 'PINAK_SALT').digest('hex').substring(0, 16);

    // 5. Save to Supabase
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
      return res.status(500).json({ error: 'Failed to record log to database.' });
    }

    return res.status(200).json({
      success: true,
      message: 'Download command log recorded successfully.',
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
