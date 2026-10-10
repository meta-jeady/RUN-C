import os
import json
import base64
import msgpack
import logging
import asyncio
from io import BytesIO
from urllib.parse import quote
from Crypto.Cipher import AES
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "TON_TOKEN_ICI")
KEY_256 = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
KEY_192 = b"F)J@NcRfUjXn2r4u7x!A%D*G"
IV = bytes.fromhex("232e39185523184a5723586242200e05")
SIGNATURE = "BY : kcorp tech"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
# ========================================================

def aes_decrypt(data: bytes, key: bytes) -> bytes:
    """Décrypte des données AES-CFB."""
    cipher = AES.new(key, AES.MODE_CFB, iv=IV, segment_size=128)
    return cipher.decrypt(data)

def clean_encrypted(obj, key=KEY_192):
    """Décrypte récursivement les champs dont le nom commence par Encrypted."""
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if (isinstance(k, str) and k.startswith("Encrypted") and isinstance(v, (bytes, bytearray)) and len(v) > 0):
                dec = aes_decrypt(bytes(v), key)
                try:
                    text = dec.decode("utf-8")
                    if text.startswith("{") or text.startswith("["):
                        try:
                            new[k.replace("Encrypted", "", 1)] = json.loads(text)
                        except (json.JSONDecodeError, ValueError):
                            new[k.replace("Encrypted", "", 1)] = text
                    else:
                        new[k.replace("Encrypted", "", 1)] = text
                except UnicodeDecodeError:
                    try:
                        new[k.replace("Encrypted", "", 1)] = msgpack.unpackb(dec, raw=False, strict_map_key=False)
                    except Exception:
                        new[k] = dec.hex()
            else:
                new[k] = clean_encrypted(v, key)
        return new
    elif isinstance(obj, list):
        return [clean_encrypted(item, key) for item in obj]
    else:
        return obj

def decrypt_dark(content: str | bytes) -> dict:
    """Décrypte un lien ou un contenu DarkTunnel."""
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        content = content.strip()
        if content.startswith("darktunnel://"):
            content = content[len("darktunnel://"):]
        try:
            outer_bytes = base64.urlsafe_b64decode(content + "=" * (-len(content) % 4))
            outer = json.loads(outer_bytes.decode("utf-8"))
        except Exception as exc:
            return {"error": f"Impossible de lire la structure extérieure : {exc}"}
        if not isinstance(outer, dict):
            return {"error": "La structure extérieure n'est pas un objet JSON."}
        result = {"type": outer.get("type", "Unknown"), "name": outer.get("name", "Sans nom")}
        enc_b64 = outer.get("encryptedLockedConfig", "")
        if not enc_b64:
            return result
        if isinstance(enc_b64, bytes):
            enc_b64 = enc_b64.decode("ascii")
        enc_b64 = enc_b64.strip()
        enc_b64 += "=" * (-len(enc_b64) % 4)
        try:
            enc = base64.urlsafe_b64decode(enc_b64)
        except Exception:
            enc = base64.b64decode(enc_b64)
        decrypted_outer = aes_decrypt(enc, KEY_256)
        unpacked = msgpack.unpackb(decrypted_outer, raw=False, strict_map_key=False)
        if not isinstance(unpacked, dict):
            return {"error": "La première structure décryptée n'est pas un dictionnaire."}
        if "LockedAppConfig" in unpacked:
            result["LockedAppConfig"] = unpacked["LockedAppConfig"]
        if "EncryptedLockedConfig" in unpacked:
            elc = unpacked["EncryptedLockedConfig"]
            if isinstance(elc, (bytes, bytearray)):
                decrypted_inner = aes_decrypt(bytes(elc), KEY_192)
                inner = msgpack.unpackb(decrypted_inner, raw=False, strict_map_key=False)
                result["Config"] = clean_encrypted(inner)
            elif isinstance(elc, dict):
                result["Config"] = clean_encrypted(elc)
        return result
    except Exception as exc:
        logger.exception("Erreur pendant le décryptage")
        return {"error": f"{type(exc).__name__}: {exc}"}

def json_safe(obj):
    """Convertit les valeurs non JSON en représentations lisibles."""
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            return obj.hex()
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(item) for item in obj]
    if isinstance(obj, tuple):
        return [json_safe(item) for item in obj]
    return obj

def make_txt(data: dict) -> str:
    """Crée un fichier texte avec la structure comme Scriptoolz."""
    lines = []
    lines.append("@ScriptoolzDecrypt_bot")
    lines.append("TG: https://t.me/ScriptorzDecrypt")
    lines.append("")
    lines.append("Ad: Create, share & manage VPN configs with HTTP Tweak VPN: https://t.me/HTTPTweak/9")
    lines.append("")
    lines.append(f"Requested by: {SIGNATURE}")
    lines.append("")
    
    result = {
        "type": data.get("type"),
        "name": data.get("name"),
        "vlessTunnelConfig": {
            "v2rayConfig": {
                "mux": True
            }
        },
        "encryptedLockedConfig": {}
    }
    
    if "LockedAppConfig" in data:
        result["encryptedLockedConfig"]["LockedAppConfig"] = data["LockedAppConfig"]
    
    config = data.get("Config", {})
    encrypted_locked = {}
    
    inject = config.get("InjectConfig", {})
    if inject:
        encrypted_locked["InjectConfig"] = {
            "IsEncrypted": True,
            "EncryptedMode": inject.get("Mode", "DIRECT"),
            "EncryptedProxyHost": inject.get("ProxyHost", "localhost"),
            "EncryptedProxyPort": inject.get("ProxyPort", "8080"),
            "EncryptedPayload": inject.get("Payload", ""),
            "EncryptedDnsttDnsHost": inject.get("DnsttDnsHost", "1.1.1.1"),
            "EncryptedDnsttDnsPort": inject.get("DnsttDnsPort", "53")
        }
        if inject.get("ServerNameIndication"):
            encrypted_locked["InjectConfig"]["EncryptedServerNameIndication"] = inject.get("ServerNameIndication", "")
        if inject.get("DnsttServerName"):
            encrypted_locked["InjectConfig"]["EncryptedDnsttServerName"] = inject.get("DnsttServerName", "")
        if inject.get("DnsttPubkey"):
            encrypted_locked["InjectConfig"]["EncryptedDnsttPubkey"] = inject.get("DnsttPubkey", "")
    
    ssh = config.get("SshConfig", {})
    if ssh:
        encrypted_locked["SshConfig"] = {
            "IsEncrypted": True,
            "IsLocked": True,
            "EncryptedPort": ssh.get("Port", "80")
        }
        if ssh.get("Host"):
            encrypted_locked["SshConfig"]["EncryptedHost"] = ssh.get("Host", "")
        if ssh.get("Username"):
            encrypted_locked["SshConfig"]["EncryptedUsername"] = ssh.get("Username", "")
        if ssh.get("Password"):
            encrypted_locked["SshConfig"]["EncryptedPassword"] = ssh.get("Password", "")
    
    v2ray = config.get("V2RayConfig", {})
    if v2ray:
        v2ray_config = v2ray.get("Config", "")
        parsed_config = {}
        
        if isinstance(v2ray_config, str):
            try:
                parsed_config = json.loads(v2ray_config)
            except:
                parsed_config = v2ray_config
        elif isinstance(v2ray_config, dict):
            parsed_config = v2ray_config
            
        encrypted_locked["V2RayConfig"] = {
            "IsEncrypted": True,
            "IsInjectModeEnabled": v2ray.get("IsInjectModeEnabled", False),
            "EncryptedConfig": parsed_config
        }
    
    result["encryptedLockedConfig"]["EncryptedLockedConfig"] = encrypted_locked
    
    lines.append(json.dumps(json_safe(result), indent=4, ensure_ascii=False))
    
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start."""
    if update.message is None:
        return
    await update.message.reply_text(
        "🔓 DarkTunnel Decryptor\n\n"
        "Envoie-moi un fichier.dark ou un lien darktunnel://...\n\n"
        "Je vais analyser la configuration et, si le format "
        "et les clés sont compatibles, générer un fichier.txt "
        "avec la structure obtenue.\n\n"
        f"{SIGNATURE}"
    )

async def process_and_reply(update: Update, content: str | bytes, original_name: str = "config"):
    """Analyse une configuration et renvoie uniquement le fichier.txt."""
    if update.message is None:
        return
    
    await update.message.reply_text("⏳ Analyse et décryptage en cours...")
    
    data = decrypt_dark(content)
    if "error" in data:
        await update.message.reply_text(f"❌ Échec du décryptage :\n{data['error']}")
        return
    
    txt_content = make_txt(data)
    safe_name = os.path.basename(original_name or "config")
    if safe_name.lower().endswith(".dark"):
        safe_name = safe_name[:-5]
    safe_name = safe_name.replace(" ", "_")
    filename = f"{safe_name or 'config'}-decrypted.txt"
    
    file_buffer = BytesIO(txt_content.encode("utf-8"))
    file_buffer.seek(0)
    await update.message.reply_document(
        document=InputFile(file_buffer, filename=filename),
        caption=f"📁 Structure analysée\n{SIGNATURE}",
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite les liens reçus en message."""
    if update.message is None:
        return
    texte = update.message.text or ""
    if "darktunnel://" not in texte.lower():
        await update.message.reply_text("Envoie un lien darktunnel://... ou un fichier.dark.")
        return
    start_index = texte.lower().find("darktunnel://")
    lien = texte[start_index:].strip()
    lien = lien.split()[0].strip()
    await process_and_reply(update, lien, "darktunnel")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite les fichiers envoyés au bot."""
    if update.message is None or update.message.document is None:
        return
    doc = update.message.document
    filename = doc.file_name or "config"
    if not filename.lower().endswith(".dark"):
        await update.message.reply_text("❌ Envoie un fichier portant l'extension.dark.")
        return
    try:
        telegram_file = await context.bot.get_file(doc.file_id)
        buffer = BytesIO()
        await telegram_file.download_to_memory(buffer)
        content = buffer.getvalue()
        await process_and_reply(update, content, filename)
    except Exception as exc:
        logger.exception("Erreur lors du téléchargement du document")
        await update.message.reply_text(f"❌ Impossible de traiter le fichier : {type(exc).__name__}: {exc}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Enregistre les erreurs du bot."""
    logger.error("Erreur pendant le traitement d'une mise à jour", exc_info=context.error)

async def run_bot():
    """Lance le bot avec gestion asyncio correcte pour Render."""
    if not BOT_TOKEN or BOT_TOKEN == "TON_TOKEN_ICI":
        logger.error("BOT_TOKEN non défini. Configure cette variable dans les variables d'environnement de Render.")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_error_handler(error_handler)

    logger.info("DarkTunnel Decryptor démarre... %s", SIGNATURE)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()

def main():
    """Point d'entrée avec boucle asyncio."""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot arrêté manuellement")

if __name__ == "__main__":
    main()
