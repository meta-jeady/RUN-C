import os, json, base64, msgpack
from io import BytesIO
from Crypto.Cipher import AES
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
SIGNATURE = "BY : kcorp tech"
KEY_256 = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
KEY_192 = b"F)J@NcRfUjXn2r4u7x!A%D*G"
IV = bytes.fromhex("232e39185523184a5723586242200e05")

def aes_decrypt(data, key):
    return AES.new(key, AES.MODE_CFB, IV, segment_size=128).decrypt(data)

def try_parse_json(s):
    if not isinstance(s, str): return s
    s = s.strip()
    if s.startswith("{") or s.startswith("["):
        try: return json.loads(s)
        except: pass
    return s

def clean_value(v, key=KEY_192):
    if not isinstance(v, (bytes, bytearray)) or len(v)==0:
        return try_parse_json(v) if isinstance(v, str) else v
    dec = aes_decrypt(v, key)
    try:
        text = dec.decode("utf-8")
        parsed = try_parse_json(text)
        return parsed
    except:
        try:
            return msgpack.unpackb(dec, raw=False, strict_map_key=False)
        except:
            return dec.hex()

def clean_section(section):
    if not isinstance(section, dict): return section
    out = {}
    for k, v in section.items():
        if isinstance(v, (bytes, bytearray)):
            # Tous les champs Encrypted
            cleaned = clean_value(v)
            # Si c'est encore une string JSON, on la parse
            if isinstance(cleaned, str):
                cleaned = try_parse_json(cleaned)
            out[k] = cleaned
        elif isinstance(v, dict):
            out[k] = clean_section(v)
        elif isinstance(v, list):
            out[k] = [clean_section(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = try_parse_json(v) if isinstance(v, str) else v
    # Cas spécial: EncryptedConfig est souvent string JSON -> forcer le parse
    if "EncryptedConfig" in out and isinstance(out["EncryptedConfig"], str):
        out["EncryptedConfig"] = try_parse_json(out["EncryptedConfig"])
    return out

def decrypt_dark(content):
    try:
        if isinstance(content, bytes): content = content.decode("utf-8", errors="ignore")
        content = content.strip()
        if content.startswith("darktunnel://"): content = content[len("darktunnel://"):]

        outer = json.loads(base64.b64decode(content).decode())
        result = {"type": outer.get("type"), "name": outer.get("name")}

        enc_b64 = outer.get("encryptedLockedConfig", "")
        enc_b64 += "=" * (-len(enc_b64) % 4)
        try: enc = base64.urlsafe_b64decode(enc_b64)
        except: enc = base64.b64decode(enc_b64)

        unpacked = msgpack.unpackb(aes_decrypt(enc, KEY_256), raw=False, strict_map_key=False)

        lac = unpacked.get("LockedAppConfig", {})
        locked_clean = {k: (v.decode() if isinstance(v, bytes) else v) for k,v in lac.items()}

        elc = unpacked.get("EncryptedLockedConfig")
        inner_clean = {}
        if isinstance(elc, (bytes, bytearray)):
            inner = msgpack.unpackb(aes_decrypt(elc, KEY_192), raw=False, strict_map_key=False)
            for sec_name, sec_data in inner.items():
                inner_clean[sec_name] = clean_section(sec_data)

        result["vlessTunnelConfig"] = {"v2rayConfig": {"mux": True}} if result["type"]=="VLESS" else {}
        result["encryptedLockedConfig"] = {
            "LockedAppConfig": locked_clean,
            "EncryptedLockedConfig": inner_clean
        }
        return result
    except Exception as e:
        return {"error": str(e)}

def make_dark_txt(data):
    return json.dumps(data, indent=4, ensure_ascii=False, default=str)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔓 DarkTunnel Decryptor\nEnvoie.dark\n_{SIGNATURE}_", parse_mode="Markdown")

async def process(update, content, name="config"):
    await update.message.reply_text("⏳ Décryptage en cours...")
    data = decrypt_dark(content)
    if "error" in data:
        await update.message.reply_text(f"❌ {data['error']}")
        return
    txt = make_dark_txt(data)
    # Resume VLESS si present
    try:
        v = data["encryptedLockedConfig"]["EncryptedLockedConfig"]["V2RayConfig"]["EncryptedConfig"]
        if isinstance(v, str): v = json.loads(v)
        out = v["outbounds"][0]
        addr = out["settings"]["vnext"][0]["address"] if "vnext" in out["settings"] else out["settings"]["servers"][0]["address"]
        await update.message.reply_text(f"✅ **{data.get('name')}**\n`{addr}` décrypté\n\n```json\n{txt[:3500]}\n```", parse_mode="Markdown")
    except:
        await update.message.reply_text(f"```json\n{txt[:3500]}\n```", parse_mode="Markdown")

    await update.message.reply_document(
        InputFile(BytesIO(txt.encode()), filename=f"{name}-decrypted.json"),
        caption=f"✅ Décrypté - {SIGNATURE}"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    f = await context.bot.get_file(doc.file_id)
    buf = BytesIO()
    await f.download_to_memory(buf)
    await process(update, buf.getvalue(), doc.file_name)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process(update, update.message.text, "darktunnel")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print(f"Bot démarré {SIGNATURE}")
    app.run_polling()

if __name__ == "__main__":
    main()
