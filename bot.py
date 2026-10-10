import os
import json
import base64
import msgpack
from io import BytesIO
from Crypto.Cipher import AES
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "TON_TOKEN_ICI")

KEY_256 = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
KEY_192 = b"F)J@NcRfUjXn2r4u7x!A%D*G"
IV = bytes.fromhex("232e39185523184a5723586242200e05")

SIGNATURE = "BY : kcorp tech"
# ================================================


def aes_decrypt(data: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_CFB, IV, segment_size=128)
    return cipher.decrypt(data)


def clean_encrypted(obj, key=KEY_192):
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k.startswith("Encrypted") and isinstance(v, (bytes, bytearray)) and len(v) > 0:
                dec = aes_decrypt(v, key)
                try:
                    new[k.replace("Encrypted", "")] = dec.decode("utf-8")
                except:
                    try:
                        new[k.replace("Encrypted", "")] = msgpack.unpackb(dec, raw=False, strict_map_key=False)
                    except:
                        new[k] = dec.hex()
            else:
                new[k] = clean_encrypted(v, key)
        return new
    elif isinstance(obj, list):
        return [clean_encrypted(i, key) for i in obj]
    else:
        return obj


def decrypt_dark(content: str | bytes) -> dict | None:
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")

        content = content.strip()
        if content.startswith("darktunnel://"):
            content = content[len("darktunnel://"):]

        outer = json.loads(base64.b64decode(content).decode())

        result = {
            "type": outer.get("type", "Unknown"),
            "name": outer.get("name", "Sans nom"),
        }

        enc_b64 = outer.get("encryptedLockedConfig", "")
        if not enc_b64:
            return result

        enc_b64 += "=" * (-len(enc_b64) % 4)
        try:
            enc = base64.urlsafe_b64decode(enc_b64)
        except:
            enc = base64.b64decode(enc_b64)

        unpacked = msgpack.unpackb(aes_decrypt(enc, KEY_256), raw=False, strict_map_key=False)

        if "LockedAppConfig" in unpacked:
            result["LockedAppConfig"] = unpacked["LockedAppConfig"]

        if "EncryptedLockedConfig" in unpacked:
            elc = unpacked["EncryptedLockedConfig"]
            if isinstance(elc, (bytes, bytearray)):
                inner = msgpack.unpackb(aes_decrypt(elc, KEY_192), raw=False, strict_map_key=False)
                result["Config"] = clean_encrypted(inner)

        return result
    except Exception as e:
        return {"error": str(e)}


def make_txt(data: dict) -> str:
    lines = []
    lines.append("=" * 50)
    lines.append("       DARKTUNNEL - CONFIG DÉCRYPTÉE")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"Type : {data.get('type', '?')}")
    lines.append(f"Nom  : {data.get('name', '?')}")
    lines.append("")

    config = data.get("Config", {})
    v2ray = config.get("V2RayConfig", {})
    raw_config = v2ray.get("Config", "")

    if isinstance(raw_config, str) and raw_config.startswith("{"):
        try:
            xray = json.loads(raw_config)
            outbound = xray.get("outbounds", [{}])[0]
            settings = outbound.get("settings", {}).get("vnext", [{}])[0]
            stream = outbound.get("streamSettings", {})

            address = settings.get("address", "?")
            port = settings.get("port", "?")
            user = settings.get("users", [{}])[0]
            uuid = user.get("id", "?")

            tls = stream.get("tlsSettings", {})
            sni = tls.get("serverName", "")
            ws = stream.get("wsSettings", {})
            host = ws.get("headers", {}).get("Host", "")
            path = ws.get("path", "")

            lines.append("-" * 40)
            lines.append("CHAMPS DARKTUNNEL")
            lines.append("-" * 40)
            lines.append("")
            lines.append("Target server :")
            lines.append(f"{address}:{port}")
            lines.append("")
            lines.append("UUID :")
            lines.append(uuid)
            lines.append("")
            lines.append("Path :")
            lines.append(path)
            lines.append("")
            lines.append("Server Name Indication (SNI) :")
            lines.append(sni)
            lines.append("")
            lines.append("Header Host :")
            lines.append(host)
            lines.append("")
            lines.append("-" * 40)
            lines.append("LIEN VLESS COMPLET")
            lines.append("-" * 40)
            lines.append("")

            path_enc = path.replace("/", "%2F")
            vless = (
                f"vless://{uuid}@{address}:{port}"
                f"?encryption=none&security=tls&sni={sni}"
                f"&type=ws&host={host}&path={path_enc}"
                f"#{data.get('name', 'DarkTunnel')}"
            )
            lines.append(vless)
            lines.append("")

        except Exception as e:
            lines.append(f"Erreur extraction : {e}")
            lines.append("")
            lines.append("Config brute :")
            lines.append(str(raw_config)[:2000])
    else:
        lines.append("Contenu décrypté :")
        lines.append(json.dumps(config, indent=2, ensure_ascii=False)[:3000])

    lines.append("")
    lines.append("=" * 50)
    lines.append(f"              {SIGNATURE}")
    lines.append("=" * 50)
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔓 *DarkTunnel Decryptor*\n\n"
        "Envoie-moi un fichier `.dark` ou un lien `darktunnel://...`\n\n"
        "Je décrypte et je te renvoie un fichier `.txt` avec toutes les infos.\n\n"
        f"_{SIGNATURE}_",
        parse_mode="Markdown",
    )


async def process_and_reply(update: Update, content: str | bytes, original_name: str = "config"):
    await update.message.reply_text("⏳ Décryptage en cours...")

    data = decrypt_dark(content)

    if "error" in data:
        await update.message.reply_text(f"❌ Erreur : `{data['error']}`", parse_mode="Markdown")
        return

    txt_content = make_txt(data)
    filename = f"{original_name.replace('.dark', '')}-decrypted.txt"

    resume = txt_content[:3500]
    await update.message.reply_text(f"```\n{resume}\n```", parse_mode="Markdown")

    await update.message.reply_document(
        document=InputFile(BytesIO(txt_content.encode("utf-8")), filename=filename),
        caption=f"📁 Fichier décrypté\n\n{SIGNATURE}",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = update.message.text or ""
    if "darktunnel://" not in texte.lower():
        await update.message.reply_text("Envoie un lien `darktunnel://...` ou un fichier `.dark`")
        return
    await process_and_reply(update, texte, "darktunnel")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    filename = (doc.file_name or "").lower()
    if not (filename.endswith(".dark") or "dark" in filename):
        await update.message.reply_text("Envoie un fichier `.dark`")
        return

    file = await context.bot.get_file(doc.file_id)
    buffer = BytesIO()
    await file.download_to_memory(buffer)
    content = buffer.getvalue()

    name = doc.file_name or "config"
    await process_and_reply(update, content, name)


def main():
    if not BOT_TOKEN or BOT_TOKEN == "TON_TOKEN_ICI":
        print("❌ BOT_TOKEN non défini")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print(f"🔓 DarkTunnel Decryptor démarré... {SIGNATURE}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
