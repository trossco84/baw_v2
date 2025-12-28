create table if not exists agents (
    id serial primary key,
    name text unique not null
);

create table if not exists players (
    id serial primary key,
    player_id text unique not null,
    display_name text,
    agent_id integer references agents(id)
);

create table if not exists weeks (
    week_id date primary key
);

create table if not exists weekly_raw (
    week_id date references weeks(week_id),
    player_id text references players(player_id),
    week_amount numeric,
    pending numeric,
    scraped_at timestamp default now(),
    primary key (week_id, player_id)
);

create table if not exists manual_slips (
    id serial primary key,
    week_id date references weeks(week_id),
    player_id text references players(player_id),
    amount numeric,
    note text,
    created_at timestamp default now()
);

create table if not exists weekly_player_status (
    week_id date references weeks(week_id),
    player_id text references players(player_id),
    engaged boolean default false,
    paid boolean default false,
    updated_at timestamp default now(),
    primary key (week_id, player_id)
);
