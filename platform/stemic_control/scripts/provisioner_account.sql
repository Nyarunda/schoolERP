-- A limited MariaDB account for the Stemic provisioner, instead of root. Run once as root:
--
--     sudo mariadb < provisioner_account.sql          (after replacing CHANGE-ME with a long random password)
--
-- Then give the workers its name and password through the environment (README: Secrets):
--     STEMIC_DB_ROOT_USERNAME=stemic_provisioner
--     STEMIC_DB_ROOT_PASSWORD=<the password>
--
-- What it can do: create and drop school databases (sch_...) and the throwaway restore-check copies (restorecheck_...),
-- create the database login each school site uses and give it that one database, and flush privileges. It cannot read
-- or change any other database on the server.
-- Limit to know about: MariaDB's CREATE USER privilege (needed to create each school's login) also allows dropping
-- other logins. It cannot read their data, but it could break another application's login.

CREATE USER IF NOT EXISTS 'stemic_provisioner'@'localhost' IDENTIFIED BY 'CHANGE-ME';
CREATE USER IF NOT EXISTS 'stemic_provisioner'@'127.0.0.1' IDENTIFIED BY 'CHANGE-ME';

GRANT CREATE USER, RELOAD ON *.* TO 'stemic_provisioner'@'localhost', 'stemic_provisioner'@'127.0.0.1';
GRANT ALL PRIVILEGES ON `sch\_%`.* TO 'stemic_provisioner'@'localhost', 'stemic_provisioner'@'127.0.0.1' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON `restorecheck\_%`.* TO 'stemic_provisioner'@'localhost', 'stemic_provisioner'@'127.0.0.1' WITH GRANT OPTION;
-- the provisioner checks a school's login does not exist yet before creating it
GRANT SELECT (User, Host) ON mysql.user TO 'stemic_provisioner'@'localhost', 'stemic_provisioner'@'127.0.0.1';

FLUSH PRIVILEGES;
