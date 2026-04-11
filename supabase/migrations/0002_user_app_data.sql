-- =============================================================================
-- Migration: 0002_user_app_data.sql
-- Stores per-user app state blob so data is account-scoped, not device-scoped.
-- =============================================================================

create table if not exists user_app_data (
    user_id     uuid        primary key references auth.users(id) on delete cascade,
    data        jsonb       not null default '{}'::jsonb,
    updated_at  timestamptz not null default now()
);

alter table user_app_data enable row level security;

-- Single policy: each authenticated user can only read/write their own row.
drop policy if exists "user_app_data_owner" on user_app_data;
create policy "user_app_data_owner"
    on user_app_data
    for all
    using  (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- auto-update updated_at
drop trigger if exists trg_user_app_data_updated_at on user_app_data;
create trigger trg_user_app_data_updated_at
    before update on user_app_data
    for each row execute function set_updated_at();

-- =============================================================================
-- End of migration 0002
-- =============================================================================
