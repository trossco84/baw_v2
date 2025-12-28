-- BAW v2 Database Schema with Player History Support
-- This schema handles player ID reuse over time by tracking unique player instances

-- Agents table (unchanged)
create table if not exists agents (
    id serial primary key,
    name text unique not null
);

-- Player instances - tracks each unique combination of player_id + display_name + agent
-- This allows the same player_id to be used by different people over time
create table if not exists player_instances (
    id serial primary key,
    player_id text not null,  -- e.g., "pyr103"
    display_name text,         -- e.g., "John Doe"
    agent_id integer references agents(id),
    first_seen date not null,  -- First week this player instance appeared
    last_seen date,            -- Last week this player instance appeared (null if current)
    is_current boolean default true,  -- Is this the currently active player with this ID?
    created_at timestamp default now(),

    -- Composite unique constraint: same player_id can exist multiple times with different names/agents
    unique (player_id, display_name, agent_id),

    -- Index for fast lookups
    check (display_name is not null or display_name != '')
);

-- Index for finding current players
create index if not exists idx_player_instances_current
    on player_instances(player_id, is_current)
    where is_current = true;

-- Index for date range queries
create index if not exists idx_player_instances_dates
    on player_instances(first_seen, last_seen);

-- Weeks table (unchanged)
create table if not exists weeks (
    week_id date primary key
);

-- Weekly raw data - now references player_instances instead of player_id directly
create table if not exists weekly_raw (
    week_id date references weeks(week_id),
    player_instance_id integer references player_instances(id),
    week_amount numeric,
    pending numeric,
    scraped_at timestamp default now(),
    primary key (week_id, player_instance_id)
);

-- Manual slips - now references player_instances
create table if not exists manual_slips (
    id serial primary key,
    week_id date references weeks(week_id),
    player_instance_id integer references player_instances(id),
    amount numeric,
    note text,
    created_at timestamp default now()
);

-- Weekly player status - now references player_instances
create table if not exists weekly_player_status (
    week_id date references weeks(week_id),
    player_instance_id integer references player_instances(id),
    engaged boolean default false,
    paid boolean default false,
    updated_at timestamp default now(),
    primary key (week_id, player_instance_id)
);

-- Indexes for performance
create index if not exists idx_weekly_raw_week on weekly_raw(week_id);
create index if not exists idx_weekly_raw_player on weekly_raw(player_instance_id);
create index if not exists idx_manual_slips_week on manual_slips(week_id);
create index if not exists idx_manual_slips_player on manual_slips(player_instance_id);

-- View to simplify queries - shows current players with their IDs and names
create or replace view current_players as
select
    pi.id,
    pi.player_id,
    pi.display_name,
    pi.agent_id,
    a.name as agent_name,
    pi.first_seen,
    pi.last_seen
from player_instances pi
join agents a on a.id = pi.agent_id
where pi.is_current = true;

-- View to show all player instances with their active periods
create or replace view player_history as
select
    pi.id,
    pi.player_id,
    pi.display_name,
    pi.agent_id,
    a.name as agent_name,
    pi.first_seen,
    pi.last_seen,
    pi.is_current,
    case
        when pi.is_current then 'Active'
        else 'Historical'
    end as status
from player_instances pi
join agents a on a.id = pi.agent_id
order by pi.player_id, pi.first_seen desc;

-- Function to get or create player instance
-- This handles the logic of finding the right player instance or creating a new one
create or replace function get_or_create_player_instance(
    p_player_id text,
    p_display_name text,
    p_agent_id integer,
    p_week_id date
) returns integer as $$
declare
    v_instance_id integer;
    v_existing_name text;
    v_existing_agent integer;
begin
    -- First, try to find exact match (player_id + display_name + agent)
    select id into v_instance_id
    from player_instances
    where player_id = p_player_id
      and display_name = p_display_name
      and agent_id = p_agent_id;

    if found then
        -- Update last_seen if this week is later
        update player_instances
        set last_seen = greatest(last_seen, p_week_id)
        where id = v_instance_id;

        return v_instance_id;
    end if;

    -- Check if there's a current player with this ID but different name/agent
    select id, display_name, agent_id into v_instance_id, v_existing_name, v_existing_agent
    from player_instances
    where player_id = p_player_id
      and is_current = true
    limit 1;

    if found then
        -- If name or agent changed, mark old instance as historical and create new one
        if v_existing_name != p_display_name or v_existing_agent != p_agent_id then
            update player_instances
            set is_current = false,
                last_seen = p_week_id - interval '1 day'
            where id = v_instance_id;

            -- Create new instance
            insert into player_instances (player_id, display_name, agent_id, first_seen, last_seen, is_current)
            values (p_player_id, p_display_name, p_agent_id, p_week_id, p_week_id, true)
            returning id into v_instance_id;

            return v_instance_id;
        end if;
    end if;

    -- No existing instance found, create new one
    insert into player_instances (player_id, display_name, agent_id, first_seen, last_seen, is_current)
    values (p_player_id, p_display_name, p_agent_id, p_week_id, p_week_id, true)
    returning id into v_instance_id;

    return v_instance_id;
end;
$$ language plpgsql;

-- Comment documentation
comment on table player_instances is 'Tracks unique player instances over time. Same player_id can exist multiple times with different names/agents.';
comment on column player_instances.first_seen is 'First week this specific player instance appeared in the data';
comment on column player_instances.last_seen is 'Last week this player instance was active (null if currently active)';
comment on column player_instances.is_current is 'True if this is the currently active player with this player_id';
comment on function get_or_create_player_instance is 'Finds existing player instance or creates new one, handling player ID reuse logic';
