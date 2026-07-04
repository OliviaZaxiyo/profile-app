# Profile app backend (Python serverless functions on Vercel)

## What's in here

- `api/signup.py` — creates a user in Postgres (RDBMS tier)
- `api/login.py` — verifies login, logs session to Upstash Redis (serverless tier)
- `api/profile.py` — creates/updates profile in MongoDB (NoSQL tier), and combines
  Postgres + MongoDB data for the profile view page
- `requirements.txt` — Python packages Vercel installs automatically
- `vercel.json` — tells Vercel these are Python 3.12 functions

## Environment variables you need to set

In your Vercel project settings (once you import this folder), go to
**Settings → Environment Variables** and add:

| Name | Where to get it |
|---|---|
| `SUPABASE_DB_URL` | Supabase → Project Settings → Database → Connection string (URI, "Session" mode) |
| `MONGODB_URI` | MongoDB Atlas → Connect → Drivers → Python connection string, with your password filled in and `/profileapp` added before the `?` |
| `UPSTASH_REDIS_REST_URL` | Upstash → your database → REST API section |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash → your database → REST API section |

**Never commit these values into your code or push them to a public GitHub repo.**
They only belong in Vercel's environment variable settings.

## Testing locally before deploying (optional but recommended)

1. Install the Vercel CLI: `npm install -g vercel`
2. In this folder, run `vercel dev`
3. It'll ask you to log in and link a project - follow the prompts
4. Create a `.env` file in this folder (already gitignored by default) with the
   four variables above
5. Test with curl:

```bash
curl -X POST http://localhost:3000/api/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123","full_name":"Test User","job_title":"Developer"}'
```

## Deploying

1. Push this folder to a GitHub repo
2. Go to vercel.com → New Project → import that repo
3. Add the 4 environment variables in the project settings before your first deploy
4. Deploy — Vercel automatically detects `api/*.py` files and turns them into
   serverless endpoints at `https://your-project.vercel.app/api/signup`, etc.

## Why three different databases

| Endpoint | Database | Why this one |
|---|---|---|
| signup | Postgres (Supabase) | Login credentials need uniqueness constraints and relational integrity |
| login (session log) | Upstash Redis | High-write, simple key-based lookups, true serverless (scales to zero) |
| profile | MongoDB Atlas | Bio/skills/links vary per user - schema-less fits better than fixed columns |
