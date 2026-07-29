# PINAK-CLI Tracking Backend

A lightweight, secure, and fast Node.js + Express backend service designed to process and verify telemetry and activity logs sent from the PINAK-CLI client. It validates incoming payloads, enforces rate limits, verifies request authenticity via HMAC signatures, and writes events securely into a Supabase database.

This server is designed to be hosted on [Render](https://render.com/) and kept awake 24/7 using UptimeRobot.

---

## 🌟 Features

* **Secure Telemetry Logging**: Exposes `POST /api/v1/track` to capture the following events:
  * `session_start` (when a user launches the CLI)
  * `session_end` (when a user exits or interrupts the CLI)
  * `command` (when a user runs normal commands)
  * `download` (when a user downloads media)
* **HMAC Signature Verification**: Validates request authenticity using a shared HMAC key (`PINAK_HMAC_SECRET`), preventing spoofed and replay attacks.
* **DDoS & Spam Protection**: Integrates Upstash Redis rate limiting to enforce a limit of 30 requests per minute per IP address.
* **Database Abstraction**: Securely stores logs in Supabase using the highly sensitive `SERVICE_ROLE_KEY`, keeping it completely hidden from the client side.
* **Keep-Awake Endpoint**: Exposes a lightweight `/ping` endpoint for monitoring tools to prevent free tier sleep cycles.

---

## 🛠️ Tech Stack

* **Runtime**: Node.js
* **Framework**: Express.js
* **Database SDK**: Supabase JS Client (Admin/Service Role context)
* **Rate Limiting**: `@upstash/ratelimit` via Redis
* **Security & Crypto**: Native Node.js `crypto` (HMAC SHA-256)

---

## 🚀 Getting Started

### Prerequisites

* Node.js (v18+)
* A Supabase project (specifically the `activity_logs` table)
* An Upstash Redis database for rate limiting

### 1. Install Dependencies

```bash
npm install
```

### 2. Environment Variables

Create a `.env` file in the root directory:

```env
# Supabase Admin Configuration
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key

# Upstash Redis Configuration (Required for Rate Limiting)
UPSTASH_REDIS_REST_URL=your-upstash-redis-url
UPSTASH_REDIS_REST_TOKEN=your-upstash-redis-token

# Security (HMAC Secret)
PINAK_HMAC_SECRET=your-shared-hmac-password
```

### 3. Running Locally

```bash
npm start
```

The server will start on port `3001`. You can test it by visiting `http://localhost:3001/ping`.

---

## 📡 API Reference

### `POST /api/v1/track`

Receives logs from the PINAK-CLI client.

**Headers:**
* `Content-Type`: `application/json`
* `x-pinak-timestamp`: Unix epoch timestamp in seconds (required for HMAC verification)
* `x-pinak-signature`: HMAC-SHA256 signature generated with `PINAK_HMAC_SECRET`

**Request Body (JSON):**
```json
{
  "activity_type": "download",
  "username": "anonymous",
  "device_id": "machine_fingerprint_hash",
  "command": "pinak download --audio",
  "url": "https://instagram.com/reel/...",
  "status": "SUCCESS",
  "mode": "audio",
  "duration": 180,
  "size": 1048576,
  "session_id": "session_uuid",
  "platform": "instagram"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Activity \"download\" recorded successfully.",
  "timestamp": "2026-07-29T18:00:00.000Z"
}
```
