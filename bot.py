import os
import re
import json
import base64
import msgpack
import asyncio
import threading
from io import BytesIO
from flask import Flask
from Crypto.Cipher import AES
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "TON_TOKEN_ICI")
UUID = "d8a6b1c2-3f4e-4a5b-8c9d-1e2f3a4b5c6d"
IP = "192.179.18.100"
PORT = 443
SNI = "crashlyticsreports-pa.googleapis.com"
PATH = "/@kcorp237"
REMARK = "@KCORP-TECH"
KEY_256 = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
KEY_192 = b"F)J@NcRfUjXn2r4u7x!A%D*G"
IV = bytes.fromhex("232e39185523184a5723586242200e05")
# ================================================

# --- Flask pour Render gratuit (anti Time Out) ---
flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return "KCORP Bot is Live"
def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

def aes_encrypt(data: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_CFB, IV, segment_size=128)
    return cipher.encrypt(data)

def extraire_host(texte: str) -> str | None:
    texte = texte.strip()
    match = re.search(r"([a-z0-9\-]+\.[a-z0-9\-]+\.run\.app)", texte, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    if "run.app" in texte.lower() and " " not in texte:
        host = texte.lower().replace("https://", "").replace("http://", "").split("/")[0]
        if host.endswith(".run.app"):
            return host
    return None

def generer_config_xray(host: str) -> str:
    config = {
        "inbounds": [{"listen": "$SOCKS5_LISTEN_HOST","port": "$SOCKS5_LISTEN_PORT","protocol": "socks","settings": {"auth": "noauth","udp": True,"userLevel": 8}},{"listen": "$HTTP_LISTEN_HOST","port": "$HTTP_LISTEN_PORT","protocol": "http","settings": {"userLevel": 8}}],
        "log": {"loglevel": "none"},
        "outbounds": [{"mux": {"concurrency": 8,"enabled": "$MUX_ENABLED"},"protocol": "vless","settings": {"vnext": [{"address": IP,"port": PORT,"users": [{"encryption": "none","id": UUID,"flow": "","level": 8,"security": "chacha20-poly1305"}]}]},"streamSettings": {"network": "ws","security": "tls","tlsSettings": {"allowInsecure": True,"serverName": SNI},"wsSettings": {"headers": {"Host": host},"path": PATH}}}],
        "policy": {"levels": {"8": {"connIdle": 300,"downlinkOnly": 1,"handshake": 4,"uplinkOnly": 1}},"system": {"statsOutboundUplink": False,"statsOutboundDownlink": False}},"stats": {}
    }
    return json.dumps(config, separators=(",", ":"))

def generer_dark_file(host: str, name: str = REMARK) -> bytes:
    inner = {
        "InjectConfig": {"IsEncrypted": True,"EncryptedMode": aes_encrypt(b"DIRECT", KEY_192),"EncryptedProxyHost": aes_encrypt(b"localhost", KEY_192),"EncryptedProxyPort": aes_encrypt(b"8080", KEY_192),"EncryptedServerNameIndication": aes_encrypt(b"", KEY_192),"EncryptedPayload": aes_encrypt(b"[method] [host_port] [protocol][crlf]Host: [host][crlf]Service: SSH[crlf]Mode: Bypass[crlf][crlf]", KEY_192),"EncryptedDnsttDnsHost": aes_encrypt(b"1.1.1.1", KEY_192),"EncryptedDnsttDnsPort": aes_encrypt(b"53", KEY_192),"EncryptedDnsttServerName": aes_encrypt(b"", KEY_192),"EncryptedDnsttPubkey": aes_encrypt(b"", KEY_192)},
        "SshConfig": {"IsEncrypted": True,"IsLocked": True,"EncryptedHost": aes_encrypt(b"", KEY_192),"EncryptedPort": aes_encrypt(b"80", KEY_192),"EncryptedUsername": aes_encrypt(b"", KEY_192),"EncryptedPassword": aes_encrypt(b"", KEY_192)},
        "V2RayConfig": {"IsEncrypted": True,"IsInjectModeEnabled": False,"EncryptedConfig": aes_encrypt(generer_config_xray(host).encode("utf-8"), KEY_192)}
    }
    inner_packed = msgpack.packb(inner, use_bin_type=True)
    encrypted_inner = aes_encrypt(inner_packed, KEY_192)
    outer_msgpack = {"LockedAppConfig": {"VersionCode": 0,"VersionName": "","Message": "","ConnectedMessage": "","Password": "","ExpiredAtTimestamp": 0,"HardwareIdList": [],"TunnelType": "VLESS","IsSshLocked": False},"EncryptedLockedConfig": encrypted_inner}
    outer_packed = msgpack.packb(outer_msgpack, use_bin_type=True)
    encrypted_outer = aes_encrypt(outer_packed, KEY_256)
    final = {"type": "VLESS","name": name,"encryptedLockedConfig": base64.urlsafe_b64encode(encrypted_outer).decode("utf-8").rstrip("=")}
    payload = base64.b64encode(json.dumps(final, separators=(",", ":")).encode("utf-8")).decode("utf-8")
    return f"darktunnel://{payload}".encode("utf-8")

def generer_lien_vless(host: str) -> str:
    path_encoded = PATH.replace("/", "%2F")
    return f"vless://{UUID}@{IP}:{PORT}?encryption=none&security=tls&sni={SNI}&type=ws&host={host}&path={path_encoded}#{REMARK}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 *KCORP DarkTunnel Bot*\n\nEnvoie le lien Cloud Run avec `.run.app`", parse_mode="Markdown")

async def traiter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    host = extraire_host(update.message.text or "")
    if not host:
        await update.message.reply_text("❌ Pas de host `.run.app` trouvé")
        return
    lien = generer_lien_vless(host)
    dark_bytes = generer_dark_file(host)
    filename = f"KCORP-{host.split('.')[0]}.dark"
    await update.message.reply_text(f"✅ Host: `{host}`\n\n`{lien}`", parse_mode="Markdown")
    await update.message.reply_document(document=InputFile(BytesIO(dark_bytes), filename=filename), caption=f"Host: `{host}`", parse_mode="Markdown")

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except:
        pass
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, traiter))
    print("🚀 Bot démarré...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
