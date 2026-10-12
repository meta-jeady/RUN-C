import os
import json
import base64
import msgpack
from io import BytesIO
from Crypto.Cipher import AES
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "TON_TOKEN_ICI")
SIGNATURE = "BY : kcorp tech"

KEY_256 = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
KEY_192 = b"F)J@NcRfUjXn2r4u7x!A%D*G"
IV = bytes.fromhex("232e39185523184a5723586242200e05")

def aes_decrypt(data, key):
    return AES.new(key, AES.MODE_CFB, IV, segment_size=128).decrypt(data)

def to_str(v):
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8")
        except:
            return v.hex()
    return v

def clean_value(v, key=KEY_192):
    if not isinstance(v, (bytes, bytearray)) or len(v) == 0:
        return to_str(v)
    dec = aes_decrypt(v, key)
    try:
        text = dec.decode("utf-8")
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except:
                return text
        return text
    except:
        try:
            return msgpack.unpackb(dec, raw=False, strict_map_key=False)
        except:
            return dec.hex()

def clean_section(section):
    if not isinstance(section, dict):
        return to_str(section)
    out = {}
    for k, v in section.items():
        if k.startswith("Encrypted") and isinstance(v, (bytes, bytearray)):
            out[k] = clean_value(v)
        elif isinstance(v, dict):
            out[k] = clean_section(v)
        elif isinstance(v, list):
            out[k] = [clean_section(i) if isinstance(i, dict) else to_str(i) for i in v]
        else:
            out[k] = to_str(v)
    return out

def decrypt_dark(content):
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

        lac = unpacked.get("LockedAppConfig", {})
        locked_clean = {k: to_str(v) for k, v in lac.items()}

        elc = unpacked.get("EncryptedLockedConfig")
        inner_clean = {}
        if isinstance(elc, (bytes, bytearray)):
            inner = msgpack.unpackb(aes_decrypt(elc, KEY_192), raw=False, strict_map_key=False)
            for section_name, section_data in inner.items():
                inner_clean[section_name] = clean_section(section_data)

        result["encryptedLockedConfig"] = {
            "LockedAppConfig": locked_clean,
            "EncryptedLockedConfig": inner_clean
        }
        return result

    except Exception as e:
        return {"error": str(e)}

def make_dark_txt(data):
    lines = []
    lines.append("=" * 55)
    lines.append(" DARKTUNNEL - DECRYPTE EN CLAIR")
    lines.append("=" * 55)
    lines.append("")

    try:
        inner = data.get("encryptedLockedConfig", {}).get("EncryptedLockedConfig", {})
        v2ray = inner.get("V2RayConfig", {})
        cfg = v2ray.get("EncryptedConfig", {})
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        if isinstance(cfg, dict):
            out = cfg.get("outbounds", [{}])[0]
            st = out.get("settings", {}).get("vnext", [{}])[0]
            stream = out.get("streamSettings", {})
            addr = st.get("address", "?")
            port = st.get("port", "?")
            uuid = st.get("users", [{}])[0].get("id", "?")
            sni = stream.get("tlsSettings", {}).get("serverName", "")
            host = stream.get("wsSettings", {}).get("headers", {}).get("Host", "")
            path = stream.get("wsSettings", {}).get("path", "")
            lines.append("-" * 45)
            lines.append("RESUME VLESS")
            lines.append("-" * 45)
            lines.append(f"Target server : {addr}:{port}")
            lines.append(f"UUID : {uuid}")
            lines.append(f"Path : {path}")
            lines.append(f"SNI : {sni}")
            lines.append(f"Header Host : {host}")
            lines.append("")
            pe = str(path).replace("/", "%2F")
            lines.append("Lien VLESS :")
            lines.append(f"vless://{uuid}@{addr}:{port}?encryption=none&security=tls&sni={sni}&type=ws&host={host}&path={pe}#{data.get('name', '')}")
            lines.append("")
    except Exception:
        pass

    lines.append("=" * 55)
    lines.append("STRUCTURE COMPLETE")
    lines.append("=" * 55)
    lines.append("")
    lines.append(json.dumps(data, indent=4, ensure_ascii=False, default=str))
    lines.append("")
    lines.append("=" * 55)
    lines.append(f" {SIGNATURE}")
    lines.append("=" * 55)
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔓 *DarkTunnel Decryptor*\n\n"
        "Envoie un fichier `.dark` ou un lien `darktunnel://...`\n\n"
        f"_{SIGNATURE}_",
        parse_mode="Markdown",
    )

async def process(update, content, name="config"):
    await update.message.reply_text("⏳ Décryptage...")
    data = decrypt_dark(content)
    if "error" in data:
        await update.message.reply_text(f"❌ `{data['error']}`", parse_mode="Markdown")
        return
    txt = make_dark_txt(data)
    await update.message.reply_text(f"```\n{txt[:3500]}\n```", parse_mode="Markdown")
    await update.message.reply_document(
        document=InputFile(BytesIO(txt.encode("utf-8")), filename=f"{name}-decrypted.txt"),
        caption=f"✅ DarkTunnel décrypté\n\n{SIGNATURE}",
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return
    filename = (doc.file_name or "").lower()
    if not filename.endswith(".dark"):
        await update.message.reply_text("Envoie un fichier `.dark`")
        return
    f = await context.bot.get_file(doc.file_id)
    buf = BytesIO()
    await f.download_to_memory(buf)
    await process(update, buf.getvalue(), doc.file_name or "config")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if "darktunnel://" not in t.lower():
        await update.message.reply_text("Envoie un fichier `.dark` ou un lien `darktunnel://`")
        return
    await process(update, t, "darktunnel")

def main():
    if not BOT_TOKEN or BOT_TOKEN == "TON_TOKEN_ICI":
        print("❌ BOT_TOKEN manquant")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print(f"🔓 DarkTunnel Decryptor démarré... {SIGNATURE}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
