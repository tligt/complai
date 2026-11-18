-- S67 (D-188), 18 Nov 2026: compliance heartbeat.
-- When monitor_heartbeat.py last emailed the company's owner, so a finding
-- that stays open is not mailed every night (at most weekly for something
-- new, monthly as a reminder). Same pattern as clients.training_nudged_at.
ALTER TABLE clients ADD COLUMN IF NOT EXISTS heartbeat_notified_at timestamptz;
