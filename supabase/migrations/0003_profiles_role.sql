-- Add role column to profiles
-- Values: 'free' | 'pro' | 'admin'
-- Default: 'free' for all existing and new users.
-- To promote yourself to admin, run the UPDATE below with your email.

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'free';

-- Seed: set owner account to admin
-- Replace with your actual email before running.
-- UPDATE profiles SET role = 'admin' WHERE email = 'pivo.news@gmail.com';
