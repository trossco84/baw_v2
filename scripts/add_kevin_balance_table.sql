-- Migration to add kevin_balance tracking table
-- This table tracks Kevin's (pyr109) running balance for the $100 bubble logic

-- Create kevin_balance table
CREATE TABLE IF NOT EXISTS kevin_balance (
    id SERIAL PRIMARY KEY,
    player_instance_id INTEGER NOT NULL REFERENCES player_instances(id),
    current_balance DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (player_instance_id)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_kevin_balance_player_instance
    ON kevin_balance(player_instance_id);

-- Add comment
COMMENT ON TABLE kevin_balance IS 'Tracks Kevin (pyr109) running balance for $100 bubble logic. Balance accumulates until it exceeds ±$100, then is applied to weekly settlement.';

-- Initialize Kevin's balance if he exists
DO $$
DECLARE
    kevin_instance_id INTEGER;
BEGIN
    -- Find Kevin's current player instance
    SELECT id INTO kevin_instance_id
    FROM player_instances
    WHERE player_id = 'pyr109' AND is_current = true
    LIMIT 1;

    -- If Kevin exists, initialize his balance
    IF kevin_instance_id IS NOT NULL THEN
        INSERT INTO kevin_balance (player_instance_id, current_balance)
        VALUES (kevin_instance_id, 0.00)
        ON CONFLICT (player_instance_id) DO NOTHING;

        RAISE NOTICE 'Initialized Kevin balance tracking for instance %', kevin_instance_id;
    ELSE
        RAISE NOTICE 'Kevin (pyr109) not found in current players';
    END IF;
END $$;
