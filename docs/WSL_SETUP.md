# Run schoolERP locally on Windows (WSL) and test before pushing

This guide takes a Windows 10/11 PC from nothing to a running ERPNext v16 + schoolERP site, then shows the test routine to follow before every `git push`.

Time: about 45–60 minutes the first time. Everything after section 1 runs **inside Ubuntu**, not in PowerShell.

Versions used by Frappe/ERPNext v16: **Ubuntu 24.04, Python 3.14, Node 24, MariaDB 11.8, Redis, wkhtmltopdf 0.12.6.1 (patched Qt)**.

---

## 1. Install WSL with Ubuntu 24.04 (Windows side)

Open **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart when asked. Ubuntu opens and asks you for a Linux username and password (remember the password; `sudo` needs it).

Recommended: give WSL enough memory. Create `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=6GB
processors=4
```

Then in PowerShell: `wsl --shutdown` and reopen Ubuntu.

Make sure systemd is on (needed so MariaDB and Redis start like services). In Ubuntu:

```bash
cat /etc/wsl.conf
```

If it doesn't show `systemd=true`, run:

```bash
printf '[boot]\nsystemd=true\n' | sudo tee /etc/wsl.conf
```

and `wsl --shutdown` from PowerShell, then reopen Ubuntu.

> **Important:** keep all code in the Linux home folder (`~/...`), never under `/mnt/c/...`. Builds on the Windows drive are 10x slower and file watching breaks.
> You can still open the files from Windows Explorer at `\\wsl$\Ubuntu-24.04\home\<you>` or with VS Code's "WSL" extension (`code .` from Ubuntu).

---

## 2. System packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl build-essential pkg-config software-properties-common \
  python3-dev python3-venv libffi-dev libssl-dev libmysqlclient-dev \
  redis-server xvfb libfontconfig fontconfig xfonts-75dpi xfonts-base cron
```

### MariaDB 11.8

Ubuntu 24.04's own MariaDB is older, so use the official MariaDB repository:

```bash
curl -LsS https://r.mariadb.com/downloads/mariadb_repo_setup | sudo bash -s -- --mariadb-server-version="mariadb-11.8"
sudo apt install -y mariadb-server mariadb-client
```

Configure UTF-8 (Frappe requires it):

```bash
sudo tee /etc/mysql/mariadb.conf.d/99-frappe.cnf > /dev/null <<'EOF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4
EOF
sudo systemctl restart mariadb
```

Set the database root password (you'll type it when creating sites):

```bash
sudo mariadb-secure-installation
```

Answer: current password = Enter, switch to unix_socket = **n**, change root password = **y** (pick one, e.g. `root` for a dev machine), then **y** to the rest.

Check: `mariadb -u root -p -e "select version();"` shows 11.8.x.

### Redis

```bash
sudo systemctl enable --now redis-server
redis-cli ping     # PONG
```

### wkhtmltopdf (for PDF statements and receipts)

Must be the **patched Qt** build, not the Ubuntu package:

```bash
cd /tmp
wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_amd64.deb
sudo apt install -y ./wkhtmltox_0.12.6.1-2.jammy_amd64.deb
wkhtmltopdf --version   # must say "(with patched qt)"
```

(If your PC is ARM, use the `jammy_arm64.deb` instead.)

---

## 3. Python 3.14, Node 24, bench

```bash
# uv manages Python versions and installs bench
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv python install 3.14 --default

# Node 24 via nvm, plus yarn
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install 24
npm install -g yarn

# bench CLI
uv tool install frappe-bench
bench --version
```

Check: `python3.14 --version`, `node -v` (v24.x), `yarn -v`.

---

## 4. Create the bench with ERPNext v16

```bash
cd ~
bench init --frappe-branch version-16 --python "$(uv python find 3.14)" frappe-bench
cd frappe-bench
bench get-app --branch version-16 erpnext
```

Create two sites: one to click around in, one that tests are allowed to fill with junk.

```bash
bench new-site school.localhost --admin-password admin --install-app erpnext
bench new-site test.localhost   --admin-password admin --install-app erpnext
bench --site school.localhost set-config developer_mode 1
bench --site test.localhost set-config allow_tests true
bench use school.localhost
```

(`*.localhost` addresses already point to your PC, so no hosts-file edit is needed.)

---

## 5. Put schoolERP in a git repo and add it to the bench

Unzip the project into your home folder (from Windows, copy `schoolERP.zip` to `\\wsl$\Ubuntu-24.04\home\<you>\`):

```bash
cd ~
sudo apt install -y unzip
unzip schoolERP.zip          # creates ~/schoolERP
```

The zip already contains the git history (`git -C ~/schoolERP log` shows it).

Install it into the bench. `get-app` clones your local repo into `apps/school_erp`:

```bash
cd ~/frappe-bench
bench get-app ~/schoolERP
bench --site school.localhost install-app school_erp
bench --site test.localhost   install-app school_erp
bench build --app school_erp
```

From now on **work inside `~/frappe-bench/apps/school_erp`**. That folder is the git repo you will push from. (You can delete `~/schoolERP` afterwards.)

```bash
cd ~/frappe-bench/apps/school_erp
git remote remove origin     # it points at ~/schoolERP; GitHub is added in section 8
./scripts/install-hooks.sh   # every git push now runs the checks first
code .                       # optional: open in VS Code (WSL extension)
```

---

## 6. Run it

```bash
cd ~/frappe-bench
bench start
```

Open **http://school.localhost:8000** in your Windows browser and log in as `Administrator` / `admin`.

1. Complete the ERPNext setup wizard (country Kenya, currency KES, company name, fiscal year).
2. Search **School Settings**: fill School name, Company; set Paybill.
3. License tab: paste a license key (make one with `tools/license_tool.py`, see the main README, after putting your public key in `school_erp/licensing/public_key.py`). Save.
4. Click **Run School Setup**.
5. Set an account on **Mode of Payment → M-Pesa** (and Cash).

Leave `bench start` running in one Ubuntu terminal; use a second terminal for everything else. Stop it with `Ctrl+C`.

---

## 7. Test before every push

There are three levels. Run them in this order.

### Level 1: quick checks (seconds, automatic)

```bash
cd ~/frappe-bench/apps/school_erp
./scripts/check.sh
```

This compiles all Python, validates every DocType JSON (links, child tables, fetch fields), syntax-checks all JavaScript, and runs the business-logic unit tests (billing, payment splitting, statements, licensing). The pre-push hook runs it for you on `git push`.

### Level 2: integration tests on a real site (1–3 minutes)

```bash
cd ~/frappe-bench
bench --site test.localhost migrate        # after changing any DocType
bench --site test.localhost run-tests --app school_erp
```

This creates a student and checks: Customer created with the same ID, term billing amounts, a "transport only" payment splitting correctly, the Payment Entry posting, balances, the statement totals, duplicate M-Pesa codes rejected, cancellation reversing the money, license blocking unpaid modules, and timetable clashes.

Run one test only:

```bash
bench --site test.localhost run-tests --module school_erp.tests.test_integration --test test_bill_pay_and_statement
```

To make the pre-push hook include Level 2 automatically:

```bash
echo 'export SCHOOL_ERP_TEST_SITE=test.localhost' >> ~/.bashrc && source ~/.bashrc
```

### Level 3: manual smoke test in the browser (5 minutes)

On `school.localhost`, after `bench --site school.localhost migrate` and `bench build --app school_erp`:

- [ ] Create a stream and a student with a guardian (mark Primary). The student gets an ID like `STU-2026-0001`; a Customer with the same ID exists.
- [ ] Create a School Fee Structure for the current term; add a Transport Route; tick lunch on the student.
- [ ] Fee Billing Run → **Preview** shows the right amounts → Submit → status becomes Completed (needs `bench start` running for the background worker).
- [ ] Fee Payment → choose "Specific fee types" → Transport → Submit → print the **Fee Receipt**.
- [ ] Student → Fees → **Fee Statement (PDF)**: check it looks right and the totals match.
- [ ] Fee Balances report shows the student.
- [ ] Timetable: create one, then try to book the same teacher in another stream at the same time (should be refused). Print it.
- [ ] If you changed SMS code: set School Settings → SMS provider to Africa's Talking **Sandbox** and send a statement.

Only push when all three levels pass.

---

## 8. Push to GitHub (first time)

1. On github.com create a new **empty** repository named `schoolERP` (Private recommended; no README/licence, since the project already has them).
2. Give WSL access to GitHub (once):

   ```bash
   git config --global user.name  "Your Name"
   git config --global user.email "you@example.com"
   ssh-keygen -t ed25519 -C "you@example.com"     # press Enter to accept defaults
   cat ~/.ssh/id_ed25519.pub
   ```

   Copy the printed key into GitHub → Settings → SSH and GPG keys → New SSH key. Test with `ssh -T git@github.com`.

3. Push:

   ```bash
   cd ~/frappe-bench/apps/school_erp
   git remote add origin git@github.com:<your-username>/schoolERP.git
   git push -u origin main
   ```

The pre-push hook runs the checks first; GitHub Actions then repeats them and runs the full integration tests on a clean ERPNext v16 (see the **Actions** tab).

> Never commit `vendor.key` (your private licence key). `.gitignore` excludes `*.key`, and the check script refuses to push if one is staged.

## 9. Daily workflow

```bash
cd ~/frappe-bench/apps/school_erp
git checkout -b feature/my-change
# ...edit code...
cd ~/frappe-bench
bench --site school.localhost migrate && bench build --app school_erp   # see it in the browser
bench --site test.localhost migrate && bench --site test.localhost run-tests --app school_erp
cd apps/school_erp
git add -A && git commit -m "Describe the change"
git push -u origin feature/my-change      # hook runs checks; open a Pull Request on GitHub
```

After pulling changes made elsewhere: `bench --site school.localhost migrate`.

To install on a school server later: `bench get-app git@github.com:<your-username>/schoolERP.git`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `bench start` says port 8000/11000/13000 in use | Another bench is running: `pkill -f "bench\|redis-server.*1[13]000"` or reboot WSL with `wsl --shutdown` |
| `Access denied for user 'root'@'localhost'` on new-site | Re-run `sudo mariadb-secure-installation`, answer **n** to unix_socket, set a password |
| Site page doesn't load in Windows browser | Use `http://school.localhost:8000` (not https). If it still fails, try `http://localhost:8000` after `bench use school.localhost` |
| PDFs blank or missing styles | wkhtmltopdf isn't the patched build; reinstall from section 2 |
| `run-tests` says tests not allowed | `bench --site test.localhost set-config allow_tests true` |
| Billing run stuck on "Queued" | Background workers only run under `bench start` |
| Changes to a DocType don't show | `bench --site school.localhost migrate`, then hard refresh (Ctrl+Shift+R) |
| JavaScript changes don't show | `bench build --app school_erp` (or keep `bench watch` running) |
| "Module not part of this school's subscription" | Paste a license key that includes the module (School Settings → License) |
| WSL very slow | Code is under `/mnt/c`; move it to `~` |
