-- Grant admin role to etweinhaus@gmail.com
-- Note: This will only work if the user exists in auth.users
INSERT INTO user_roles (user_id, role)
SELECT id, 'admin'
FROM auth.users
WHERE email = 'etweinhaus@gmail.com'
ON CONFLICT (user_id) DO UPDATE
SET role = 'admin', updated_at = NOW();

