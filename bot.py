import asyncio, time, os, re, threading, urllib.parse
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

def can_use(u):
    now=time.time()
    user_usage[u]=[t for t in user_usage[u] if now-t<86400]
    return (False,"hourly") if len([t for t in user_usage[u] if now-t<3600])>=MAX_PER_HOUR else (False,"daily") if len(user_usage[u])>=MAX_PER_DAY else (True,"ok")
def record_use(u): user_usage[u].append(time.time())

VLESS_TEMPLATE="vless://d8a6b1c2-3f4e-4a5b-8c9d-1e2f3a4b5c6d@192.179.18.100:443?encryption=none&security=tls&sni=crashlyticsreports-pa.googleapis.com&type=ws&host={domain}&path=%2F@kcorp237#@KCORP-TECH"
JSON_TEMPLATE='{"dns":{"servers":["8.8.8.8"]},"inbounds":[{"port":10808,"protocol":"socks","settings":{"auth":"noauth","udp":true}}],"outbounds":[{"protocol":"vless","settings":{"vnext":[{"address":"192.179.18.100","port":443,"users":[{"id":"d8a6b1c2-3f4e-4a5b-8c9d-1e2f3a4b5c6d","encryption":"none"}]}]},"streamSettings":{"network":"ws","security":"tls","tlsSettings":{"serverName":"crashlyticsreports-pa.googleapis.com","allowInsecure":true},"wsSettings":{"path":"/@kcorp237","headers":{"Host":"__DOMAIN__"}}}}]}'

def extract_domain(url): return urlparse(url).netloc if url.startswith("http") else url.split("/")[0]
def extract_project_id(url):
    m=re.search(r'(qwiklabs-gcp-[\w-]+)', url)
    return m.group(1) if m else None

async def process_sso(sso_url: str, update: Update):
    # FIX ENCODAGE TRIPLE
    for _ in range(4): sso_url=urllib.parse.unquote(sso_url)
    project_id=extract_project_id(sso_url)
    if not project_id:
        await update.message.reply_text("❌ Lien invalide"); return
    await update.message.reply_text("⏳ Traitement NEW CODE en cours... lien <1min svp")
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--single-process","--no-zygote"])
            context=await browser.new_context(viewport={"width":1280,"height":720})
            page=await context.new_page()
            await page.goto(sso_url, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(6000)
            for name in ["I understand","I Understand","Continue","Proceed","Got it"]:
                try:
                    loc=page.get_by_role("button", name=name).first
                    if await loc.is_visible(timeout=1000): await loc.click(); await page.wait_for_timeout(1500)
                except: pass
            try: await page.keyboard.press("Enter"); await page.wait_for_timeout(2000)
            except: pass
            success=False
            for _ in range(150):
                url=(page.url or "").lower()
                if "console.cloud.google.com" in url and "accounts.google.com" not in url: success=True; break
                try:
                    if await page.get_by_role("button", name="Agree and continue").is_visible(timeout=400): success=True; break
                except: pass
                await page.wait_for_timeout(1000)
            if not success: raise Exception(f"Timeout SSO bloqué sur {page.url[:200]}")
            qs=parse_qs(urlparse(page.url).query); authuser=qs.get("authuser",[""])[0]
            try:
                agree=page.get_by_role("button", name="Agree and continue"); await agree.wait_for(timeout=12000)
                checks=page.get_by_role("checkbox"); await checks.nth(0).click(); await asyncio.sleep(0.5); await checks.nth(1).click(); await agree.click(); await page.wait_for_timeout(3000)
            except: pass
            api_url=f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}";
            if authuser: api_url+=f"&authuser={authuser}"
            await page.goto(api_url, wait_until="domcontentloaded", timeout=90000)
            enable=page.get_by_role("button", name="Enable"); manage=page.get_by_role("button", name="Manage")
            await expect(enable.or_(manage)).to_be_visible(timeout=35000)
            if await enable.is_visible(): await enable.click(); await expect(manage).to_be_visible(timeout=90000)
            run_url=f"https://console.cloud.google.com/run/create?project={project_id}"
            if authuser: run_url+=f"&authuser={authuser}"
            await page.goto(run_url, wait_until="domcontentloaded", timeout=90000); await page.wait_for_timeout(4000)
            label=page.get_by_text("Container Image URL").first; await label.click(); await page.keyboard.type("docker.io/metajeady/kcorp1", delay=35)
            await page.wait_for_timeout(1500); await page.get_by_role("radio", name="Allow public access").click(); await page.get_by_role("radio", name="Instance-based").click()
            await page.keyboard.press("End"); await page.wait_for_timeout(500); await page.get_by_role("button", name="Create").click(force=True)
            link=page.locator('a[href*="run.app"]'); await link.wait_for(state="visible", timeout=120000)
            final_url=await link.get_attribute("href"); domain=extract_domain(final_url)
            vless=VLESS_TEMPLATE.format(domain=domain)
            await update.message.reply_text(f"✅ **Config générée!**\n\n🌐 `{domain}`\n\n🔗 **VLESS :**\n`{vless}`", parse_mode="Markdown")
            json_cfg=JSON_TEMPLATE.replace("__DOMAIN__", domain)
            await update.message.reply_document(document=json_cfg.encode(), filename=f"KCORP-{domain}.json", caption="📄 Config JSON")
            record_use(update.effective_user.id); await browser.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : `{str(e)[:700]}`", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("**Bienvenue KCORP-TECH NEW CODE** ☁️\nEnvoie un lien SSO FRAIS (<1min).", parse_mode="Markdown")
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text=update.message.text.strip()
    if "google_sso" not in text and "skills.google" not in text and "cloudskillsboost" not in text: await update.message.reply_text("⚠️ Lien SSO uniquement."); return
    ok,_=can_use(update.effective_user.id)
    if not ok: await update.message.reply_text("⏳ Limite atteinte."); return
    asyncio.create_task(process_sso(text, update))
def main():
    if not BOT_TOKEN: print("❌ BOT_TOKEN manquant"); return
    flask_app=Flask(__name__)
    @flask_app.route('/')
    def home(): return "Bot KCORP OK NEW"
    threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot KCORP NEW démarré..."); app.run_polling()
if __name__=="__main__": main()
