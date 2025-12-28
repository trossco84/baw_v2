# Stats Page - Agent Performance Dashboard

## Overview

The Stats page displays all-time performance metrics for each agent in a baseball card-style layout. It's accessible via `/stats` and includes agent filtering.

## Features

### Navigation
- New "Stats" link added to all page headers (Dashboard, Upload, Manage)
- Stats page includes links back to other sections

### Baseball Card Layout

The page displays agent statistics in a classic baseball card format:

**Top Section (Header + Key Stats)**
- Agent name in large, prominent display
- Avatar placeholder with agent's first initial
- Three key characteristics:
  - **Total Volume**: Sum of absolute values of all weekly net amounts (total action)
  - **Total Revenue**: Sum of all weekly net amounts (negative = money collected)
  - **Avg Weekly Players**: Average number of players per week

**Bottom Section (3 Mini Cards)**
1. **Top 5 Revenue Generators**
   - Players who generated the most revenue (lowest/most negative totals)
   - Shows player name and total revenue
   - Color-coded: green for positive, red for negative

2. **Top 5 Biggest Losers**
   - Players who lost the most money (highest/most positive totals)
   - Shows player name and total revenue
   - Color-coded: green for positive, red for negative

3. **Best Week**
   - Week with the most revenue (lowest total)
   - Displays:
     - Week date
     - Total revenue for that week
     - Number of players that week
     - Biggest contributor (player with most revenue that week)
     - Contribution amount

### Agent Filtering

- Clickable button selector at top of page
- Shows all agents except Dro
- Active agent highlighted in blue
- Page updates when clicking different agents (URL: `/stats?agent=AgentName`)

## Database Queries

### Main Stats Query
```sql
SELECT
    SUM(ABS(wr.week_amount)) as total_volume,
    SUM(wr.week_amount) as total_revenue,
    AVG(weekly_players.player_count) as avg_player_count
FROM weekly_raw wr
JOIN player_instances pi ON pi.id = wr.player_instance_id
WHERE pi.agent_id = %s
```

### Top Players Query
```sql
SELECT
    pi.display_name,
    SUM(wr.week_amount) as total_revenue
FROM weekly_raw wr
JOIN player_instances pi ON pi.id = wr.player_instance_id
WHERE pi.agent_id = %s
GROUP BY pi.display_name, pi.player_id
ORDER BY total_revenue ASC  -- ASC for best (most negative = most revenue)
LIMIT 5
```

### Best Week Query
```sql
WITH weekly_stats AS (
    SELECT
        wr.week_id,
        SUM(wr.week_amount) as week_revenue,
        COUNT(DISTINCT wr.player_instance_id) as player_count
    FROM weekly_raw wr
    JOIN player_instances pi ON pi.id = wr.player_instance_id
    WHERE pi.agent_id = %s
    GROUP BY wr.week_id
)
SELECT week_id, week_revenue, player_count
FROM weekly_stats
ORDER BY week_revenue ASC  -- ASC for best (most negative = most revenue)
LIMIT 1
```

## Styling

The page uses a premium card design with:
- Gradient backgrounds
- Blue accent color for headers and highlights
- Circular avatar placeholder
- Responsive grid layout (3 columns on desktop, stacks on mobile)
- Tabular numbers for all currency values
- Color-coded positive/negative values

## Files Modified

- `app/main.py` - Added `/stats` route with database queries
- `app/templates/stats.html` - New template with baseball card layout
- `app/templates/dashboard.html` - Added Stats link to navigation
- `app/templates/upload.html` - Added Stats link to navigation
- `app/templates/manage.html` - Added Stats link to navigation

## Usage

1. Navigate to `/stats` or click "Stats" link in any page header
2. Default agent (first alphabetically) is selected automatically
3. Click agent buttons at top to switch between agents
4. View all-time performance metrics for selected agent

## Sign Convention

Remember: In this system, negative values represent revenue (player losses), positive values represent player wins.

- **Total Revenue** = negative is good (we collected money)
- **Best Players** = most negative totals (generated most revenue)
- **Worst Players** = most positive totals (lost us the most money)
- **Best Week** = most negative week total (most revenue that week)

## Future Enhancements

Potential additions:
- Week-by-week trend charts
- Player win/loss records
- Average bet sizes
- Season comparisons
- Export to PDF or CSV
- Agent profile pictures instead of placeholder
