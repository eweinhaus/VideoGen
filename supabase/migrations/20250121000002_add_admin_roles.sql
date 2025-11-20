-- Add admin role support to allow certain users to view all jobs
-- This migration adds a user_roles table and updates RLS policies

-- Create user_roles table to track admin users
CREATE TABLE IF NOT EXISTS user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'admin')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id)
);

-- Enable RLS on user_roles
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;

-- Policy: Users can view their own role
CREATE POLICY "Users can view own role"
  ON user_roles FOR SELECT
  USING (auth.uid() = user_id);

-- Policy: Only service role can manage roles (backend only)
CREATE POLICY "Service role can manage roles"
  ON user_roles FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Create helper function to check if current user is admin
CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM user_roles
    WHERE user_id = auth.uid()
    AND role = 'admin'
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Update RLS policies to allow admins to see all jobs

-- Drop existing policies
DROP POLICY IF EXISTS "Users can view own jobs" ON jobs;
DROP POLICY IF EXISTS "Users can view own job stages" ON job_stages;
DROP POLICY IF EXISTS "Users can view own job costs" ON job_costs;

-- Recreate policies with admin access
CREATE POLICY "Users can view own jobs or admins can view all"
  ON jobs FOR SELECT
  USING (auth.uid() = user_id OR is_admin());

CREATE POLICY "Users can view own job stages or admins can view all"
  ON job_stages FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs WHERE jobs.id = job_stages.job_id AND jobs.user_id = auth.uid()
    ) OR is_admin()
  );

CREATE POLICY "Users can view own job costs or admins can view all"
  ON job_costs FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs WHERE jobs.id = job_costs.job_id AND jobs.user_id = auth.uid()
    ) OR is_admin()
  );

-- Grant admin role to myles93@sbcglobal.net
-- Note: This will only work if the user exists in auth.users
INSERT INTO user_roles (user_id, role)
SELECT id, 'admin'
FROM auth.users
WHERE email = 'myles93@sbcglobal.net'
ON CONFLICT (user_id) DO UPDATE
SET role = 'admin', updated_at = NOW();

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role);

