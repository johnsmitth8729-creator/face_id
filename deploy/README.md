# Ubuntu Production Deployment Guide for AKHU AFIVS

This guide outlines the steps to deploy the Face Identity Verification System on an Ubuntu 22.04 / 24.04 LTS server using **Gunicorn**, **Nginx**, **PostgreSQL**, and **Redis**.

---

## 1. Prerequisites & System Setup

Update the system and install required system packages:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git nginx redis-server postgresql postgresql-contrib libpq-dev libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0
```

---

## 2. Clone Repository & Setup Virtual Environment

1. Clone your project to `/var/www/akhu_verification`:
   ```bash
   sudo mkdir -p /var/www/akhu_verification
   sudo chown -R $USER:www-data /var/www/akhu_verification
   git clone <YOUR_GITHUB_REPO_URL> /var/www/akhu_verification
   ```

2. Create virtual environment and install requirements:
   ```bash
   cd /var/www/akhu_verification
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## 3. Database & Redis Setup

1. Login to PostgreSQL and create database/user:
   ```bash
   sudo -i -u postgres psql
   ```
   ```sql
   CREATE DATABASE akhu_verification;
   CREATE USER postgres WITH PASSWORD 'your_secure_password';
   GRANT ALL PRIVILEGES ON DATABASE akhu_verification TO postgres;
   \q
   ```

2. Start and enable Redis:
   ```bash
   sudo systemctl enable redis-server --now
   ```

---

## 4. Environment Variables (`.env`)

Create a production `.env` file in the root directory `/var/www/akhu_verification/.env`:
```ini
DEBUG=False
SECRET_KEY=generate_a_random_long_secret_key_here
ALLOWED_HOSTS=faceid.akhu.uz,verification.akhu.uz

# Database
DATABASE_URL=postgresql://postgres:your_secure_password@127.0.0.1:5432/akhu_verification

# Redis
REDIS_URL=redis://127.0.0.1:6379/0

# AI settings
AI_ENGINE_MODE=insightface
FACE_MATCH_THRESHOLD_VERIFIED=0.82
FACE_MATCH_THRESHOLD_REVIEW=0.68
```

---

## 5. Django Initial Setup

Run migrations, compile translations, and collect static files:
```bash
source venv/bin/activate
python manage.py migrate
python manage.py compilemessages
python manage.py collectstatic --noinput
```

---

## 6. Configure Gunicorn

1. Copy systemd service files:
   ```bash
   sudo cp deploy/gunicorn.socket /etc/systemd/system/
   sudo cp deploy/gunicorn.service /etc/systemd/system/
   ```

2. Start and enable Gunicorn daemon:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start gunicorn.socket
   sudo systemctl enable gunicorn.socket
   ```

3. Verify socket status:
   ```bash
   sudo systemctl status gunicorn.socket
   ```

---

## 7. Configure Nginx & SSL (Certbot)

1. Copy Nginx server configuration:
   ```bash
   sudo cp deploy/nginx.conf /etc/nginx/sites-available/akhu_verification
   sudo ln -s /etc/nginx/sites-available/akhu_verification /etc/nginx/sites-enabled/
   ```

2. Test Nginx configuration and reload:
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```

3. Set up SSL using Certbot (Let's Encrypt):
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d faceid.akhu.uz -d verification.akhu.uz
   ```
