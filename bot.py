import os, json, base64, msgpack, re
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

def try_parse_json(s):
    if isinstance(s, (bytes, bytearray)):
        try: s = s.decode('utf-8', errors='ignore')
        except: return s
    if not isinstance(s, str): return s
    s = s.strip()
    if s.startswith("{") or s.startswith("["):
        try: return json.loads(s)
        except: pass
    return s

def clean_value(v):
    if not isinstance(v, (bytes, bytearray)) or len(v)==0:
        return try_parse_json(v) if isinstance(v, str) else v
    try:
        dec = aes_decrypt(v, KEY_192)
        try:
            txt = dec.decode('utf-8', errors='ignore')
            parsed = try_parse_json(txt)
            if parsed!= txt or txt.strip().startswith("{"):
                return parsed
            return txt if txt else dec.hex()
        except:
            try: return msgpack.unpackb(dec, raw=False, strict_map_key=False)
            except: return dec.hex()
    except:
        return v.hex()[:300]

def clean_section(section):
    if not isinstance(section, dict): return section
    out = {}
    for k, v in section.items():
        if isinstance(v, (bytes, bytearray)):
            out[k] = clean_value(v)
        elif isinstance(v, dict):
            out[k] = clean_section(v)
        elif isinstance(v, list):
            out[k] = [clean_section(i) if isinstance(i, dict) else try_parse_json(i) for i in v]
        else:
            out[k] = try_parse_json(v) if isinstance(v, str) else v
    if "EncryptedConfig" in out and isinstance(out["EncryptedConfig"], str):
        out["EncryptedConfig"] = try_parse_json(out["EncryptedConfig"])
    return out

def decrypt_dark(content):
    try:
        if isinstance(content, bytes):
            raw = content.decode('utf-8', errors='ignore')
        else:
            raw = str(content)
        raw = raw.strip()
        if raw.lower().startswith("darktunnel://"):
            raw = raw[len("darktunnel://"):]

        # FIX pour ton erreur ASCII : on garde que les caracteres base64 valides
        if "encryptedLockedConfig" in raw:
            outer = json.loads(raw)
        else:
            b64_only = "".join(re.findall(r'[A-Za-z0-9+/=_-]+', raw))
            b64_only += "=" * (-len(b64_only) % 4)
            try: outer_bytes = base64.urlsafe_b64decode(b64_only)
            except: outer_bytes = base64.b64decode(b64_only)
            outer = json.loads(outer_bytes.decode('utf-8', errors='ignore'))

        result = {"type": outer.get("type"), "name": outer.get("name", "Sans nom")}
        enc_b64 = str(outer.get("encryptedLockedConfig", ""))
        enc_b64 = "".join(re.findall(r'[A-Za-z0-9+/=_-]+', enc_b64))
        enc_b64 += "=" * (-len(enc_b64) % 4)
        try: enc = base64.urlsafe_b64decode(enc_b64)
        except: enc = base64.b64decode(enc_b64)

        unpacked = msgpack.unpackb(aes_decrypt(enc, KEY_256), raw=False, strict_map_key=False)
        lac = unpacked.get("LockedAppConfig", {})
        locked_clean = {k: (v.decode('utf-8', errors='ignore') if isinstance(v, (bytes, bytearray)) else v) for k,v in lac.items()}

        elc = unpacked.get("EncryptedLockedConfig")
        inner_clean = {}
        if isinstance(elc, (bytes, bytearray)):
            inner = msgpack.unpackb(aes_decrypt(elc, KEY_192), raw=False, strict_map_key=False)
            for name, sec in inner.items():
                inner_clean[name] = clean_section(sec)

        result["vlessTunnelConfig"] = {"v2rayConfig": {"mux": True}} if result["type"]=="VLESS" else {}
        result["encryptedLockedConfig"] = {"LockedAppConfig": locked_clean, "EncryptedLockedConfig": inner_clean}
        return result
    except Exception as e:
        return {"error": str(e)}

def make_dark_txt(data):
    lines = []
    lines.append("="*55)
    lines.append(" DARKTUNNEL - DECRYPTE EN CLAIR")
    lines.append("="*55)
    lines.append("")
    try:
        inner = data.get("encryptedLockedConfig", {}).get("EncryptedLockedConfig", {})
        v2ray = inner.get("V2RayConfig", {}).get("EncryptedConfig", {})
        if isinstance(v2ray, str): v2ray = json.loads(v2ray)
        if isinstance(v2ray, dict):
            out = v2ray.get("outbounds", [{}])[0]
            settings = out.get("settings", {})
            vnext = settings.get("vnext", [{}])[0] if "vnext" in settings else settings.get("servers", [{}])[0]
            stream = out.get("streamSettings", {})
            addr = vnext.get("address", "?")
            port = vnext.get("port", "?")
            uuid = vnext.get("id") or vnext.get("users", [{}])[0].get("id", "?")
            if isinstance(uuid, dict): uuid = "?"
            sni = stream.get("tlsSettings", {}).get("serverName", "")
            host = stream.get("wsSettings", {}).get("headers", {}).get("Host", "")
            path = stream.get("wsSettings", {}).get("path", "")
            lines.append(f"Target server : {addr}:{port}")
            lines.append(f"UUID : {uuid}")
            lines.append(f"Path : {path}")
            lines.append(f"SNI : {sni}")
            lines.append(f"Header Host : {host}")
            lines.append("")
            pe = str(path).replace("/", "%2F")
            lines.append(f"vless://{uuid}@{addr}:{port}?encryption=none&security=tls&sni={sni}&type=ws&host={host}&path={pe}#{data.get('name','')}")
            lines.append("")
    except: pass
    lines.append("="*55)
    lines.append("STRUCTURE COMPLETE")
    lines.append("="*55)
    lines.append(json.dumps(data, indent=4, ensure_ascii=False, default=str))
    lines.append("")
    lines.append(SIGNATURE)
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔓 *DarkTunnel Decryptor*\nEnvoie.dark\n_{SIGNATURE}_", parse_mode="Markdown")

async def process(update, content, name="config"):
    m = await update.message.reply_text("⏳ Décryptage en cours...")
    data = decrypt_dark(content)
    if "error" in data:
        await m.edit_text(f"❌ `{data['error']}`", parse_mode="Markdown")
        return
    txt = make_dark_txt(data)
    await m.edit_text(f"✅ {data.get('name')} décrypté", parse_mode="Markdown")
    await update.message.reply_text(f"```\n{txt[:3800]}\n```", parse_mode="Markdown")
    await update.message.reply_document(InputFile(BytesIO(txt.encode('utf-8')), filename=f"{name}-decrypted.txt"), caption=f"✅ {SIGNATURE}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    f = await context.bot.get_file(update.message.document.file_id)
    buf = BytesIO()
    await f.download_to_memory(buf)
    await process(update, buf.getvalue(), update.message.document.file_name)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process(update, update.message.text, "darktunnel")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot demarre")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
