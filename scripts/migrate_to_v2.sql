-- Migration script from v1 schema to v2 schema
-- This script preserves existing data while adding player instance tracking

-- WARNING: This migration will modify your database structure
-- BACKUP YOUR DATABASE BEFORE RUNNING THIS SCRIPT
-- Run this with: psql $DATABASE_URL -f scripts/migrate_to_v2.sql

begin;

-- Step 1: Create new player_instances table
create table if not exists player_instances (
    id serial primary key,
    player_id text not null,
    display_name text,
    agent_id integer references agents(id),
    first_seen date not null,
    last_seen date,
    is_current boolean default true,
    created_at timestamp default now(),
    unique (player_id, display_name, agent_id)
);

create index if not exists idx_player_instances_current
    on player_instances(player_id, is_current)
    where is_current = true;

create index if not exists idx_player_instances_dates
    on player_instances(first_seen, last_seen);

-- Step 2: Migrate existing players to player_instances
-- For each player, find their first and last week in weekly_raw
insert into player_instances (player_id, display_name, agent_id, first_seen, last_seen, is_current)
select
    p.player_id,
    p.display_name,
    p.agent_id,
    coalesce(min(wr.week_id), current_date) as first_seen,
    max(wr.week_id) as last_seen,
    true as is_current  -- Assume all existing players are current
from players p
left join weekly_raw wr on wr.player_id = p.player_id
group by p.player_id, p.display_name, p.agent_id
on conflict (player_id, display_name, agent_id) do nothing;

-- Step 3: Add player_instance_id columns to related tables
alter table weekly_raw add column if not exists player_instance_id integer references player_instances(id);
alter table manual_slips add column if not exists player_instance_id integer references player_instances(id);
alter table weekly_player_status add column if not exists player_instance_id integer references player_instances(id);

-- Step 4: Populate player_instance_id in weekly_raw
update weekly_raw wr
set player_instance_id = pi.id
from player_instances pi
where wr.player_id = pi.player_id
  and wr.player_instance_id is null;

-- Step 5: Populate player_instance_id in manual_slips
update manual_slips ms
set player_instance_id = pi.id
from player_instances pi
where ms.player_id = pi.player_id
  and ms.player_instance_id is null
  and pi.is_current = true;  -- Use current player instance for manual slips

-- Step 6: Populate player_instance_id in weekly_player_status
update weekly_player_status wps
set player_instance_id = pi.id
from player_instances pi
where wps.player_id = pi.player_id
  and wps.player_instance_id is null;

-- Step 7: Drop old foreign key constraints
alter table weekly_raw drop constraint if exists weekly_raw_player_id_fkey;
alter table manual_slips drop constraint if exists manual_slips_player_id_fkey;
alter table weekly_player_status drop constraint if exists weekly_player_status_player_id_fkey;

-- Step 8: Drop old primary key constraints and recreate with player_instance_id
alter table weekly_raw drop constraint if exists weekly_raw_pkey;
alter table weekly_raw add primary key (week_id, player_instance_id);

alter table weekly_player_status drop constraint if exists weekly_player_status_pkey;
alter table weekly_player_status add primary key (week_id, player_instance_id);

-- Step 9: Make player_instance_id not null (all should be populated now)
alter table weekly_raw alter column player_instance_id set not null;
alter table manual_slips alter column player_instance_id set not null;
alter table weekly_player_status alter column player_instance_id set not null;

-- Step 10: Create indexes for performance
create index if not exists idx_weekly_raw_week on weekly_raw(week_id);
create index if not exists idx_weekly_raw_player_instance on weekly_raw(player_instance_id);
create index if not exists idx_manual_slips_week on manual_slips(week_id);
create index if not exists idx_manual_slips_player_instance on manual_slips(player_instance_id);

-- Step 11: Create helper views
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

-- Step 12: Create helper function for getting/creating player instances
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

-- Step 13: Verify migration
do $$
declare
    v_old_players_count integer;
    v_new_instances_count integer;
    v_weekly_raw_unmapped integer;
begin
    select count(*) into v_old_players_count from players;
    select count(*) into v_new_instances_count from player_instances;
    select count(*) into v_weekly_raw_unmapped from weekly_raw where player_instance_id is null;

    raise notice 'Migration verification:';
    raise notice '  Old players table: % rows', v_old_players_count;
    raise notice '  New player_instances table: % rows', v_new_instances_count;
    raise notice '  Unmapped weekly_raw records: %', v_weekly_raw_unmapped;

    if v_weekly_raw_unmapped > 0 then
        raise warning 'Some weekly_raw records were not mapped to player instances!';
    end if;
end $$;

-- Note: The old 'players' table is kept for reference but is no longer used
-- You can drop it after verifying the migration worked correctly:
-- DROP TABLE players;

commit;

-- Post-migration verification queries:

-- Check player instances
-- SELECT * FROM player_history ORDER BY player_id, first_seen;

-- Check for any unmapped records
-- SELECT * FROM weekly_raw WHERE player_instance_id IS NULL;
-- SELECT * FROM manual_slips WHERE player_instance_id IS NULL;

-- Compare counts
-- SELECT 'Old players' as source, COUNT(*) as count FROM players
-- UNION ALL
-- SELECT 'New player instances' as source, COUNT(*) as count FROM player_instances;
