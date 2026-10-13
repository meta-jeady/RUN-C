import asyncio
import time
import os
import re
import tempfile
import shutil
import threading
from urllib.parse import urlparse, parse_qs
from collections import defaultdict

from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright, expect

BOT_TOKEN = os.getenv("BOT_TOKEN")
MAX_PER_HOUR = 3
MAX_PER_DAY = 8

user_usage = defaultdict(list)

def can_use(user_id: int):
    now = time.time()
    user_usage[user_id] = [t for t in user_usage[user_id] if now - t < 86400]
    last_hour = [t for t in user_usage[user_id] if now - t < 3600]
    if len(last_hour) >= MAX_PER_HOUR: return False, "hourly"
    if len(user_usage[user_id]) >= MAX_PER_DAY: return False, "daily"
    return True, "ok"

def record_use(user_id: int):
    user_usage[user_id].append(time.time())

VLESS_TEMPLATE = (
    "vless://d8a6b1c2-3f4e-4a5b-8c9d-1e2f3a4b5c6d@192.179.18.100:443"
    "?encryption=none&security=tls&sni=crashlyticsreports-pa.googleapis.com"
    "&type=ws&host={domain}&path=%2F@kcorp237#@KCORP-TECH"
)

JSON_TEMPLATE = '''{
  "dns": { "servers": ["8.8.8.8"] },
  "inbounds": [{ "port": 10808, "protocol": "socks", "settings": { "auth": "noauth", "udp": true } }],
  "outbounds": [{
      "protocol": "vless",
      "settings": { "vnext": [{ "address": "192.179.18.100", "port": 443, "users": [{ "id": "d8a6b1c2-3f4e-4a5b-8c9d-1e2f3a4b5c6d", "encryption": "none" }] }] },
      "streamSettings": {
        "network": "ws", "security": "tls",
        "tlsSettings": { "serverName": "crashlyticsreports-pa.googleapis.com", "allowInsecure": true },
        "wsSettings": { "path": "/@kcorp237", "headers": { "Host": "__DOMAIN__" } }
      }
  }]
}'''

def extract_domain(url: str) -> str:
    if url.startswith("http"): return urlparse(url).netloc
    return url.split("/")[0]

def extract_project_id(url: str):
    m = re.search(r'(qwiklabs-gcp-[\w-]+)', url)
    return m.group(1) if m else None

async def process_sso(sso_url: str, update: Update):
    project_id = extract_project_id(sso_url)
    if not project_id:
        await update.message.reply_text("❌ Lien SSO invalide.")
        return
    await update.message.reply_text("⏳ Traitement en cours... (1 à 3 min) - Garde un lien FRAIS (<5min)")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--single-process","--no-zygote","--disable-setuid-sandbox"]
            )
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            await page.goto(sso_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(2000)
            await page.keyboard.press("Enter")
            try:
                btn = page.locator("text='I understand'")
                if await btn.is_visible(timeout=3000): await btn.click()
            except: pass

            for _ in range(120):
                url = (page.url or "").lower()
                if "/home/dashboard" in url or ("console.cloud.google.com" in url and "accounts.google.com" not in url): break
                try:
                    if await page.get_by_role("button", name="Agree and continue").is_visible(timeout=500): break
                except: pass
                await page.wait_for_timeout(1000)
            else:
                raise Exception("Timeout SSO - Lab expiré? Utilise un lien frais")

            qs = parse_qs(urlparse(page.url).query)
            authuser = qs.get("authuser", [""])[0]

            try:
                agree = page.get_by_role("button", name="Agree and continue")
                await agree.wait_for(timeout=10000)
                checks = page.get_by_role("checkbox")
                await checks.nth(0).click()
                await asyncio.sleep(0.5)
                await checks.nth(1).click()
                await agree.click()
            except: pass

            api_url = f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}"
            if authuser: api_url += f"&authuser={authuser}"
            await page.goto(api_url, wait_until="domcontentloaded", timeout=90000)
            enable = page.get_by_role("button", name="Enable")
            manage = page.get_by_role("button", name="Manage")
            await expect(enable.or_(manage)).to_be_visible(timeout=30000)
            if await enable.is_visible():
                await enable.click()
                await expect(manage).to_be_visible(timeout=90000)

            run_url = f"https://console.cloud.google.com/run/create?project={project_id}"
            if authuser: run_url += f"&authuser={authuser}"
            await page.goto(run_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(4000)
            label = page.get_by_text("Container Image URL").first
            await label.click()
            await page.keyboard.type("docker.io/metajeady/kcorp1", delay=40)
            await page.wait_for_timeout(1500)
            await page.get_by_role("radio", name="Allow public access").click()
            await page.get_by_role("radio", name="Instance-based").click()
            await page.keyboard.press("End")
            await page.wait_for_timeout(500)
            await page.get_by_role("button", name="Create").click(force=True)

            link = page.locator('a[href*="run.app"]')
            await link.wait_for(state="visible", timeout=120000)
            final_url = await link.get_attribute("href")
            domain = extract_domain(final_url)

            vless = VLESS_TEMPLATE.format(domain=domain)
            await update.message.reply_text(f"✅ **Config générée!**\n\n🌐 `{domain}`\n\n🔗 **VLESS :**\n`{vless}`", parse_mode="Markdown")
            json_cfg = JSON_TEMPLATE.replace("__DOMAIN__", domain)
            await update.message.reply_document(document=json_cfg.encode(), filename=f"KCORP-{domain}.json", caption="📄 Config JSON")
            record_use(update.effective_user.id)
            await browser.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : `{str(e)[:500]}`", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("**Bienvenue KCORP-TECH** ☁️\nEnvoie un lien SSO FRAIS Google Skills.\nLimites : 3/h • 8/j", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith("https://www.skills.google") and not text.startswith("https://www.cloudskillsboost.google"):
        await update.message.reply_text("⚠️ Envoie uniquement un lien SSO valide.")
        return
    ok, reason = can_use(update.effective_user.id)
    if not ok:
        await update.message.reply_text("⏳ Limite atteinte, réessaie plus tard.")
        return
    asyncio.create_task(process_sso(text, update))

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN manquant")
        return
    # Faux serveur web pour Render Web Service
    flask_app = Flask(__name__)
    @flask_app.route('/')
    def home(): return "Bot KCORP OK"
    threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot KCORP démarré...")
    app.run_polling()

if __name__ == "__main__":
    main()
