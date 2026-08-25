-- 创建只读账号：agent 生产接入的硬性要求——权限边界在数据库账号，不在应用代码
CREATE ROLE readonly LOGIN PASSWORD 'readonly';
GRANT CONNECT ON DATABASE insight TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
