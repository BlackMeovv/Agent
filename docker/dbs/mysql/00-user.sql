-- 创建只读账号：agent 生产接入的硬性要求——权限边界在数据库账号，不在应用代码
CREATE USER IF NOT EXISTS 'readonly'@'%' IDENTIFIED BY 'readonly';
GRANT SELECT ON deepquery.* TO 'readonly'@'%';
FLUSH PRIVILEGES;
