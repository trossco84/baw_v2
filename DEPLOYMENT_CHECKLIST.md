# BAW v2 Deployment Checklist

## What's Been Built

### ✅ Core Features Completed

1. **Excel Upload System**
   - Endpoint: `POST /upload/weekly`
   - UI: `/upload` page with drag-and-drop interface
   - Processes weekly admin exports from nojuice.ag
   - Automatic data normalization and validation

2. **Player & Agent Management**
   - Full CRUD for players and agents
   - Edit functionality for updating player details
   - UI: `/manage` page with tables and forms
   - Endpoints:
     - `GET/POST/PUT/DELETE /players`
     - `GET/POST/PUT/DELETE /agents`

3. **Manual Betslip System**
   - Add manual adjustments to weekly totals
   - Real-time recalculation of settlements
   - UI: Integrated into dashboard
   - Endpoints: `GET/POST/DELETE /slips`

4. **Dashboard with Real-Time Calculations**
   - Aggregates weekly_raw + manual_slips
   - Shows settlement transfers between agents
   - Player tracking with engaged/paid checkboxes
   - Agent-filtered detailed views

5. **Database Schema**
   - All tables defined in `scripts/init_db.sql`
   - Includes `weekly_player_status` table
   - Pydantic models for validation

6. **Historical Data Import**
   - Script: `scripts/import_historical.py`
   - Imports 248+ weeks of CSV data
   - Creates agents/players automatically
   - Dry-run mode for testing

### 📁 Key Files

**Backend:**
- `app/main.py` - FastAPI routes and endpoints (500+ lines)
- `app/models.py` - Pydantic data models
- `app/auth.py` - Basic HTTP authentication
- `engine/compute.py` - Dashboard calculations
- `engine/translate.py` - Excel import logic
- `engine/settlement.py` - Transfer algorithm

**Frontend:**
- `app/templates/dashboard.html` - Main dashboard
- `app/templates/upload.html` - Excel upload page
- `app/templates/manage.html` - Player/agent management
- `app/templates/base.html` - Base template with styling

**Database:**
- `scripts/init_db.sql` - Complete schema definition

**Scripts:**
- `scripts/import_historical.py` - Bulk historical data import
- `scripts/HISTORICAL_IMPORT_README.md` - Import documentation

---

## Pre-Deployment Steps

### 1. Database Setup

Run the schema initialization:

```bash
# Connect to your Supabase database
psql $DATABASE_URL -f scripts/init_db.sql
```

### 2. Import Historical Data

**Important:** Do a dry run first!

```bash
# Dry run to preview
python3 scripts/import_historical.py --dry-run --limit 10

# Full dry run
python3 scripts/import_historical.py --dry-run

# Actual import (after verifying dry run)
python3 scripts/import_historical.py
```

This will:
- Import ~248 weeks of historical data
- Create agents: Trev, Gabe, Orso, Dro
- Create ~100-150 player records
- Populate weekly_raw table

### 3. Environment Variables

Ensure these are set in your Fly.io deployment:

```bash
DATABASE_URL=postgresql://...your-supabase-pooler-url...
ADMIN_PASSWORD=your-password-here
ADMIN_SITE_PASSWORD=your-site-password-here
```

### 4. Test Locally

```bash
# Start the FastAPI server
uvicorn app.main:app --reload

# Visit http://localhost:8000
# Test:
# - Login works
# - Dashboard loads with historical data
# - Upload new weekly Excel
# - Add manual betslip
# - Edit player details
```

---

## Deployment to Fly.io

### First Time Deployment

```bash
# Login to Fly.io
fly auth login

# Deploy
fly deploy

# Set secrets
fly secrets set DATABASE_URL="your-supabase-url"
fly secrets set ADMIN_PASSWORD="your-password"
fly secrets set ADMIN_SITE_PASSWORD="your-site-password"

# Check status
fly status

# View logs
fly logs
```

### Subsequent Deployments

```bash
fly deploy
```

---

## Post-Deployment Verification

### 1. Check Database

```sql
-- Verify weeks imported
SELECT COUNT(*) FROM weeks;
-- Expected: ~248

-- Verify players
SELECT COUNT(*) FROM players;
-- Expected: 100-150

-- Verify agents
SELECT COUNT(*) FROM agents;
-- Expected: 3-4 (Trev, Gabe, Orso, Dro)

-- Check most recent week
SELECT w.week_id, COUNT(*) as players, SUM(wr.week_amount) as total
FROM weekly_raw wr
JOIN weeks w ON w.week_id = wr.week_id
GROUP BY w.week_id
ORDER BY w.week_id DESC
LIMIT 5;
```

### 2. Test User Workflows

**Monday Workflow:**
1. Visit `/upload`
2. Upload weekly Excel export from nojuice.ag
3. Return to dashboard
4. Add manual betslips if needed
5. Review settlement transfers
6. Mark players as engaged/paid

**Player Management:**
1. Visit `/manage`
2. Add new player (if needed)
3. Edit player details
4. Update agent assignment

### 3. Verify Calculations

Check that:
- Book totals are correct
- Settlement transfers balance out
- Manual slips are included in totals
- Agent filters work properly

---

## Known Limitations & Future Improvements

### Current State
- Simple basic auth (not production-grade)
- No user roles/permissions
- Manual Excel upload (not automated scraping)
- No historical week browsing (dashboard shows latest week only)
- No mobile optimization

### Future Enhancements

**Short-term (Next Phase):**
1. Week selector - Browse historical weeks
2. Better error messages - Toast notifications instead of alerts
3. Loading states - Spinners during async operations
4. Search/filter - For player lists in management
5. Mobile responsive - Better mobile layouts

**Medium-term:**
1. User authentication - Proper auth system (Supabase Auth)
2. Role-based access - Agents can only see their own data
3. Insights page - Per-agent and per-player analytics
4. Export functionality - Download reports as CSV/PDF
5. Email notifications - Weekly summaries

**Long-term:**
1. API scraper integration - Automatic weekly data fetch
2. Multi-week analysis - Trends and patterns
3. Player notes - Add context to player accounts
4. Audit log - Track all changes

---

## Troubleshooting

### Dashboard shows no data
- Check that historical import completed successfully
- Verify `weeks` table has records
- Check `weekly_raw` table has data

### Excel upload fails
- Verify file is .xlsx or .xls format
- Check that player IDs in Excel match `pyr\d+` pattern
- Ensure "Mon (MM/DD)" column header exists for week detection

### Manual betslip not updating totals
- Refresh the page (betslips require page reload)
- Check that player exists in database
- Verify week_id matches current week

### Authentication not working
- Check `ADMIN_PASSWORD` environment variable is set
- Username should be "admin"
- Clear browser cache/cookies

### Database connection errors
- Verify `DATABASE_URL` is correct
- Check Supabase pooler is accessible
- Ensure Fly.io has network access to Supabase

---

## Support & Maintenance

### Regular Tasks

**Weekly:**
- Upload new weekly Excel export
- Review and add manual betslips
- Mark players as paid

**Monthly:**
- Review player list for accuracy
- Update display names if needed
- Check for orphaned/inactive players

**As Needed:**
- Add new players when they join
- Update agent assignments
- Adjust player display names

### Monitoring

Check these regularly:
- Fly.io app health: `fly status`
- Application logs: `fly logs`
- Database size: Supabase dashboard
- Error rates: Check logs for exceptions

---

## Quick Reference

### Useful Commands

```bash
# Deploy changes
fly deploy

# View logs
fly logs

# SSH into app
fly ssh console

# Check database
fly postgres connect -a your-db-app

# Restart app
fly apps restart baw-v2
```

### Important URLs

- **Production App**: `https://baw-v2.fly.dev`
- **Dashboard**: `/`
- **Upload**: `/upload`
- **Management**: `/manage`
- **API Docs**: `/docs` (auto-generated by FastAPI)

### Database Schema Quick Ref

```
agents (id, name)
players (id, player_id, display_name, agent_id)
weeks (week_id)
weekly_raw (week_id, player_id, week_amount, pending, scraped_at)
manual_slips (id, week_id, player_id, amount, note, created_at)
weekly_player_status (week_id, player_id, engaged, paid, updated_at)
```
