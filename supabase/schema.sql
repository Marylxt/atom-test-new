-- =============================================================
-- Atoms Demo · Supabase 数据模型
-- 使用方式：Supabase 控制台 → SQL Editor → 新建查询 → 粘贴执行
-- =============================================================

-- -------------------------------------------------------------
-- 0. 扩展
-- -------------------------------------------------------------
create extension if not exists "pgcrypto";   -- gen_random_uuid()

-- -------------------------------------------------------------
-- 1. profiles · 用户档案（与 auth.users 一一对应）
-- -------------------------------------------------------------
create table if not exists public.profiles (
    id          uuid primary key,                      -- = auth.users.id
    email       text,
    display_name text,
    avatar_url  text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

comment on table public.profiles is '用户档案，主键等于 auth.users.id';

-- 注册后自动建档
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, email, display_name)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data ->> 'display_name', split_part(coalesce(new.email, ''), '@', 1))
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- -------------------------------------------------------------
-- 2. projects · 项目（一个项目 = 一个被 AI 生成出来的小应用）
-- -------------------------------------------------------------
create table if not exists public.projects (
    id                 uuid primary key default gen_random_uuid(),
    user_id            uuid not null,                            -- 归属用户 = auth.users.id
    name               text not null,
    description        text,
    status             text not null default 'draft',            -- draft | generating | ready | failed
    current_version_id uuid,                                     -- 当前生效版本（后续加外键）
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    constraint projects_status_check check (status in ('draft', 'generating', 'ready', 'failed')),
    constraint projects_name_check check (char_length(name) between 1 and 120)
);

comment on table public.projects is 'AI 生成的应用项目';

-- -------------------------------------------------------------
-- 3. versions · 版本（每一次生成 / 修改都落一条快照）
-- -------------------------------------------------------------
create table if not exists public.versions (
    id                 uuid primary key default gen_random_uuid(),
    project_id         uuid not null references public.projects (id) on delete cascade,
    version_no         integer not null,
    prompt             text not null,                            -- 触发本次生成的需求 / 修改要求
    product_spec       text,                                     -- Agent 1 产品经理产出
    architecture       text,                                     -- Agent 2 架构师产出
    html_code          text not null,                            -- Agent 3 工程师产出
    review             text,                                     -- 可选：测试工程师评审结论
    change_type        text not null default 'create',           -- create | modify | rollback
    parent_version_id  uuid references public.versions (id) on delete set null,
    model              text,
    duration_ms        integer,
    created_at         timestamptz not null default now(),
    constraint versions_change_type_check check (change_type in ('create', 'modify', 'rollback')),
    constraint versions_unique_no unique (project_id, version_no)
);

comment on table public.versions is '生成版本快照，支持多轮修改与版本回滚';

-- projects.current_version_id 外键（放在 versions 建表之后，避免循环依赖）
do $$
begin
    if not exists (
        select 1 from information_schema.table_constraints
        where constraint_name = 'projects_current_version_fk'
    ) then
        alter table public.projects
            add constraint projects_current_version_fk
            foreign key (current_version_id) references public.versions (id) on delete set null;
    end if;
end;
$$;

-- -------------------------------------------------------------
-- 4. publications · 发布记录（生成公开访问链接）
-- -------------------------------------------------------------
create table if not exists public.publications (
    id          uuid primary key default gen_random_uuid(),
    project_id  uuid not null references public.projects (id) on delete cascade,
    version_id  uuid not null references public.versions (id) on delete cascade,
    public_id   text not null unique,                            -- 短链 ID，出现在 /app/{public_id}
    title       text,
    views       integer not null default 0,
    is_active   boolean not null default true,
    created_at  timestamptz not null default now()
);

comment on table public.publications is '应用发布记录，public_id 用于公开访问';

-- -------------------------------------------------------------
-- 5. generation_events · 生成过程日志（SSE 推送的进度可回溯）
-- -------------------------------------------------------------
create table if not exists public.generation_events (
    id          bigserial primary key,
    project_id  uuid not null references public.projects (id) on delete cascade,
    version_id  uuid references public.versions (id) on delete set null,
    stage       text not null,                                   -- pm | architect | engineer | qa | system
    level       text not null default 'info',                    -- info | warn | error
    message     text not null,
    created_at  timestamptz not null default now()
);

comment on table public.generation_events is '多智能体接力的过程日志';

-- -------------------------------------------------------------
-- 6. 索引
-- -------------------------------------------------------------
create index if not exists idx_projects_user        on public.projects (user_id, updated_at desc);
create index if not exists idx_versions_project     on public.versions (project_id, version_no desc);
create index if not exists idx_pub_project          on public.publications (project_id, created_at desc);
create index if not exists idx_pub_public_id        on public.publications (public_id) where is_active;
create index if not exists idx_events_project       on public.generation_events (project_id, created_at desc);

-- -------------------------------------------------------------
-- 7. updated_at 自动维护
-- -------------------------------------------------------------
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_projects_touch on public.projects;
create trigger trg_projects_touch
    before update on public.projects
    for each row execute function public.touch_updated_at();

drop trigger if exists trg_profiles_touch on public.profiles;
create trigger trg_profiles_touch
    before update on public.profiles
    for each row execute function public.touch_updated_at();

-- -------------------------------------------------------------
-- 8. 浏览量自增（公开页每次访问 +1）
-- -------------------------------------------------------------
create or replace function public.increment_publication_views(p_public_id text)
returns void
language sql
security definer
set search_path = public
as $$
    update public.publications
       set views = views + 1
     where public_id = p_public_id;
$$;

-- -------------------------------------------------------------
-- 9. 行级安全策略（RLS）
--    后端用 service_role_key 访问，绕过 RLS；
--    这里的策略保证「前端直连 Supabase 也不会越权」。
-- -------------------------------------------------------------
alter table public.profiles          enable row level security;
alter table public.projects          enable row level security;
alter table public.versions          enable row level security;
alter table public.publications      enable row level security;
alter table public.generation_events enable row level security;

-- profiles：本人可见可改
drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
    for select using (auth.uid() = id);

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
    for update using (auth.uid() = id);

-- projects：本人可见可改
drop policy if exists projects_rw_own on public.projects;
create policy projects_rw_own on public.projects
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- versions：只能操作自己项目下的版本
drop policy if exists versions_rw_own on public.versions;
create policy versions_rw_own on public.versions
    for all using (
        exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid())
    ) with check (
        exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid())
    );

-- publications：本人可管理；已发布的记录允许匿名读取（公开访问页）
drop policy if exists publications_rw_own on public.publications;
create policy publications_rw_own on public.publications
    for all using (
        exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid())
    ) with check (
        exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid())
    );

drop policy if exists publications_public_read on public.publications;
create policy publications_public_read on public.publications
    for select using (is_active = true);

-- generation_events：本人项目可见
drop policy if exists events_rw_own on public.generation_events;
create policy events_rw_own on public.generation_events
    for all using (
        exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid())
    ) with check (
        exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid())
    );

-- -------------------------------------------------------------
-- 10. 视图：项目列表带上最新版本信息（前端列表页可直接用）
-- -------------------------------------------------------------
create or replace view public.project_overview as
select
    p.id,
    p.user_id,
    p.name,
    p.description,
    p.status,
    p.current_version_id,
    p.created_at,
    p.updated_at,
    coalesce(v.version_count, 0)  as version_count,
    v.latest_version_no,
    v.latest_created_at
from public.projects p
left join (
    select
        project_id,
        count(*)                as version_count,
        max(version_no)         as latest_version_no,
        max(created_at)         as latest_created_at
    from public.versions
    group by project_id
) v on v.project_id = p.id;

-- -------------------------------------------------------------
-- 11. 显式授权
--     说明：在 Dashboard 的 SQL Editor 里执行时，Supabase 会自动套用
--     默认权限；但通过 Management API（/v1/projects/{ref}/database/query）
--     执行时不会，会出现 42501 "permission denied for table projects"。
--     所以这里显式授权，让两种执行方式结果一致。
--     RLS 仍然生效，授权 ≠ 越权。
-- -------------------------------------------------------------
grant usage on schema public to anon, authenticated, service_role;

grant all privileges on all tables in schema public to anon, authenticated, service_role;
grant all privileges on all sequences in schema public to anon, authenticated, service_role;
grant all privileges on all functions in schema public to anon, authenticated, service_role;

-- 之后新建的对象也自动带同样的权限，避免再次出现"建了表却读不到"
alter default privileges in schema public
    grant all privileges on tables to anon, authenticated, service_role;
alter default privileges in schema public
    grant all privileges on sequences to anon, authenticated, service_role;
alter default privileges in schema public
    grant all privileges on functions to anon, authenticated, service_role;

-- 公开页只需要读，anonymous 之外的角色也一并用上面策略控制
grant select on public.project_overview to anon, authenticated, service_role;

-- =============================================================
-- 完成。可在 Table Editor 中确认 5 张表 + 1 个视图已创建。
-- =============================================================
