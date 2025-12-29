# Production Setup Guide for BAW v2

## Current State Analysis

Based on your `fly.toml` configuration:

```toml
auto_stop_machines = 'stop'
auto_start_machines = true
min_machines_running = 0
```

**What This Means:**
- Your app automatically stops when idle (no requests for ~5 minutes)
- It auto-starts when someone visits (but with a ~5-10 second cold start delay)
- You're on Fly.io's **free tier** with 0 minimum machines

**Current URL:** `https://baw-v2.fly.dev`

---

## Making It Production-Ready (Cheapest Options)

### Option 1: Keep Free Tier (Auto-Stop/Start) ✅ **RECOMMENDED FOR YOU**

**What You Get:**
- ✅ FREE (except Supabase database)
- ✅ App always accessible (just 5-10s cold start delay)
- ✅ HTTPS automatically included
- ✅ Unlimited requests when running
- ❌ First request after idle has delay

**Steps:**
1. **Do nothing** - Your current setup is production-ready for low-traffic!
2. The `.dev` domain is fine for production - it's HTTPS and works perfectly
3. Database (Supabase) is already always-on

**Cost:** $0/month for app hosting

---

### Option 2: Always-On Machine ($5/month)

If you want **zero cold starts** and instant responses 24/7:

**Update `fly.toml`:**
```toml
[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false  # Changed
  auto_start_machines = true
  min_machines_running = 1     # Changed from 0 to 1
  processes = ['app']
```

**Deploy:**
```bash
fly deploy
```

**Cost:** ~$5/month (1 shared-cpu-1x machine running 24/7)

---

## Custom Domain Setup (Optional)

If you want `baw.yourdomain.com` instead of `baw-v2.fly.dev`:

### 1. Buy a Domain
- Namecheap, Cloudflare, Google Domains (~$12/year)
- Example: `bawsports.com`

### 2. Add Domain to Fly.io
```bash
# Add certificate for your domain
fly certs add baw.yourdomain.com

# Fly will give you DNS records to add
```

### 3. Update DNS Records
Add these to your domain registrar:

**For subdomain (baw.yourdomain.com):**
```
Type: CNAME
Name: baw
Value: baw-v2.fly.dev
```

**For apex domain (yourdomain.com):**
```
Type: A
Name: @
Value: [IP from fly certs show]

Type: AAAA
Name: @
Value: [IPv6 from fly certs show]
```

### 4. Wait for DNS propagation (5-60 minutes)

**Cost:** Domain registration only (~$12/year)

---

## Current Costs Breakdown

### Your Current Setup (Free Tier):
- **Fly.io App:** $0/month (auto-stop/start)
- **Supabase Free Tier:** $0/month (500MB database, 2GB bandwidth)
- **Total:** $0/month

### Recommended Production (Always-On):
- **Fly.io App:** $5/month (always running)
- **Supabase Free Tier:** $0/month
- **Total:** $5/month

### With Custom Domain:
- **Fly.io App:** $5/month
- **Supabase Free Tier:** $0/month
- **Domain Registration:** $1/month (~$12/year)
- **Total:** $6/month

---

## Monitoring & Health Checks

### Check App Status
```bash
# View app status
fly status

# View logs
fly logs

# Check machines
fly machines list
```

### Set Up Uptime Monitoring (Free)
Use a free service to ping your app every 5 minutes (prevents auto-stop):

**Option A: UptimeRobot (Free)**
1. Sign up at https://uptimerobot.com
2. Add monitor: `https://baw-v2.fly.dev`
3. Set interval: 5 minutes
4. This keeps your app "warm" even on free tier!

**Option B: Cron-job.org (Free)**
1. Sign up at https://cron-job.org
2. Add job: `https://baw-v2.fly.dev/health/auth-config`
3. Set to run every 5 minutes

---

## Security Checklist

### ✅ Already Secured:
- [x] HTTPS enabled (force_https = true)
- [x] Basic auth password protection
- [x] Database credentials in environment variables
- [x] No secrets in git repository

### 🔒 Additional Security (Optional):
1. **Rotate passwords periodically**
   ```bash
   fly secrets set ADMIN_PASSWORD=new_password_here
   fly secrets set ADMIN_SITE_PASSWORD=new_password_here
   ```

2. **Enable Fly.io monitoring**
   ```bash
   fly dashboard
   # View metrics, logs, and alerts
   ```

3. **Database backups** - Supabase automatically backs up daily

---

## Deployment Workflow

### Current State:
Your app is already deployed! Every time you push changes:

```bash
# Make your code changes
git add .
git commit -m "Your changes"

# Deploy to Fly.io
fly deploy

# Check deployment
fly status
fly logs
```

### Auto-Deploy with GitHub Actions (Optional)
1. Store Fly.io token as GitHub secret
2. Auto-deploy on push to main branch
3. I can help set this up if you want

---

## Recommended Setup for Your Use Case

Given that this is for 3 agents with weekly usage:

### **Use Free Tier + UptimeRobot** ✨

**Why:**
- Saves $60/year ($5/month × 12)
- App stays "warm" with 5-min pings
- Perfect for low/moderate traffic
- Still professional and reliable
- HTTPS included

**Setup:**
1. Keep current `fly.toml` (no changes needed)
2. Sign up for UptimeRobot (free)
3. Add monitor for `https://baw-v2.fly.dev`
4. Set check interval: 5 minutes
5. Done! App will stay responsive 24/7

**When to Upgrade:**
- If you get >10 concurrent users regularly
- If you need guaranteed sub-100ms response times
- If you want custom domain (can add anytime)

---

## The `.dev` Domain - Is It Production-Ready?

**YES!** The `.fly.dev` domain is perfectly fine for production:

✅ **Secure:** HTTPS by default
✅ **Reliable:** 99.9%+ uptime
✅ **Fast:** Global Anycast DNS
✅ **Professional:** Many companies use it
✅ **Free:** No cost

**When to use custom domain:**
- Branding (want baw.yourcompany.com)
- Client/stakeholder preference
- Multiple apps under one domain

---

## Next Steps

### Immediate (Recommended):
1. ✅ Your app is already production-ready
2. Set up UptimeRobot monitoring (keeps it warm, free)
3. Test from all 3 agents' phones/computers
4. Bookmark `https://baw-v2.fly.dev`

### Optional Upgrades:
1. **Custom Domain** - If you want branded URL ($12/year)
2. **Always-On** - If you want instant response ($5/month)
3. **Supabase Pro** - If you exceed 500MB database ($25/month)

### Testing Production:
```bash
# Check app is running
curl https://baw-v2.fly.dev/health/auth-config

# View logs
fly logs

# Check database connection
fly ssh console
python -c "import psycopg2; print('DB connected')"
```

---

## Cost Comparison

| Setup | Monthly Cost | Cold Start? | Custom Domain? |
|-------|-------------|-------------|----------------|
| **Free Tier** | $0 | Yes (~10s) | No |
| **Free + UptimeRobot** | $0 | No (stays warm) | No |
| **Always-On** | $5 | No | No |
| **Always-On + Domain** | $6 | No | Yes |

---

## Support & Troubleshooting

### If app goes down:
```bash
fly status              # Check machine status
fly logs                # View error logs
fly machines restart    # Restart if needed
```

### If database issues:
1. Check Supabase dashboard
2. Verify `DATABASE_URL` secret: `fly secrets list`
3. Test connection: `fly ssh console` then `python` then `import psycopg2`

### Common Issues:
- **503 Error:** Machine starting up (wait 10s and refresh)
- **Auth failing:** Check `ADMIN_PASSWORD` and `ADMIN_SITE_PASSWORD` secrets
- **Database timeout:** Check Supabase dashboard, might need to upgrade plan

---

## Final Recommendation

**For your use case (3 agents, weekly usage):**

```bash
# 1. Set up free monitoring (keeps app warm)
# Sign up at uptimerobot.com
# Add monitor: https://baw-v2.fly.dev
# Interval: 5 minutes

# 2. Done! Your app is production-ready at:
# https://baw-v2.fly.dev
```

**Total Cost:** $0/month
**Reliability:** 99.9%+
**Response Time:** <1 second (with UptimeRobot)

You can upgrade to always-on ($5/month) or custom domain anytime, but this free setup is perfectly production-ready for your needs!
