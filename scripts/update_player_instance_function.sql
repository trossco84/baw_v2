-- Updated get_or_create_player_instance function
-- Simplified logic: (player_id, display_name, agent_id) is the unique key
-- If exact match exists, use it. Otherwise create new instance.

CREATE OR REPLACE FUNCTION get_or_create_player_instance(
    p_player_id text,
    p_display_name text,
    p_agent_id integer,
    p_week_id date
) RETURNS integer AS $$
DECLARE
    v_instance_id integer;
BEGIN
    -- Try to find exact match (player_id + display_name + agent)
    SELECT id INTO v_instance_id
    FROM player_instances
    WHERE player_id = p_player_id
      AND display_name = p_display_name
      AND agent_id = p_agent_id;

    IF FOUND THEN
        -- Update last_seen and ensure it's marked current
        UPDATE player_instances
        SET last_seen = GREATEST(last_seen, p_week_id),
            is_current = true
        WHERE id = v_instance_id;

        RETURN v_instance_id;
    END IF;

    -- No exact match found - create new instance
    -- First, mark any other instances with this player_id as not current
    UPDATE player_instances
    SET is_current = false
    WHERE player_id = p_player_id
      AND is_current = true;

    -- Create new instance
    INSERT INTO player_instances (player_id, display_name, agent_id, first_seen, last_seen, is_current)
    VALUES (p_player_id, p_display_name, p_agent_id, p_week_id, p_week_id, true)
    RETURNING id INTO v_instance_id;

    RETURN v_instance_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_or_create_player_instance IS 'Finds or creates player instance. Uses (player_id, display_name, agent_id) as unique key.';
