# PINAK-CLI Admin Dashboard & Command Logger

Unified Next.js 14 full-stack application replacing the legacy `server/` and `admin_server/` directories.

## Architecture

* **Public API Receiver**: `/api/v1/log-download` receives download command execution logs from `PINAK-CLI` and stores them in Supabase PostgreSQL.
* **Admin Web UI**: Next.js App Router dashboard protected by **Supabase Auth**. Displays user names, executed commands, requested links, and activity metrics.
* **Database**: Supabase PostgreSQL (`download_command_logs` table).
* **Security & DDoS Protection**: Cloudflare WAF + Upstash Redis rate limiting (10 req/min per IP).

## Setup & Environment Variables

Copy `.env.example` to `.env.local` and configure:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
PINAK_HMAC_SECRET=your-secret-key
```

## Running Locally

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to access the Admin Dashboard.
