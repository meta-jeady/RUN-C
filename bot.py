import os
import json
import base64
import msgpack
from io import BytesIO
from Crypto.Cipher import AES, ChaCha20
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "TON_TOKEN_ICI")
SIGNATURE = "BY : kcorp tech"

# DarkTunnel
KEY_256 = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
KEY_192 = b"F)J@NcRfUjXn2r4u7x!A%D*G"
IV = bytes.fromhex("232e39185523184a5723586242200e05")

# SSC / HTTP Custom ChaCha keys
SSC_KEYS = [
    bytes.fromhex("2be4342943c6f91ff58987f41a1aafd179eeb4e053f5cea55b11d6a7db58bd7d"),
    bytes.fromhex("3380aa278b744ba5b529a7f32fa803e48749280dae378345d9b526cf1dbce372"),
    bytes.fromhex("cea9305c95168b162a335b137c61983b8df54e6375da01136547890f14c5fac3"),
    bytes.fromhex("4beeace0e42bae8f29470cf40cf2dfacd5f4e1f751912bf52e803c8c85792193"),
    bytes.fromhex("f8e5f6ebea90558eb32229da24fd0fb7d813091dafe89bb2954fda33b4c60f63"),
    bytes.fromhex("81342f558a6273bac4548d473f54c4ffc7c41747dee81369acab9c787d41ab9c"),
]

# NetMod key (known, often fails on locked files)
NETMOD_KEY = base64.b64decode("X25ldHN5bmFfbmV0bW9kXw==")  # _netsyna_netmod_


def aes_decrypt(data, key):
    return AES.new(key, AES.MODE_CFB, IV, segment_size=128).decrypt(data)


def clean_encrypted(obj, key=KEY_192):
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k.startswith("Encrypted") and isinstance(v, (bytes, bytearray)) and len(v) > 0:
                dec = aes_decrypt(v, key)
                try:
                    text = dec.decode("utf-8")
                    if text.startswith("{") or text.startswith("["):
                        try:
                            new[k.replace("Encrypted", "")] = json.loads(text)
                        except:
                            new[k.replace("Encrypted", "")] = text
                    else:
                        new[k.replace("Encrypted", "")] = text
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
    return obj


def decrypt_dark(content):
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        content = content.strip()
        if content.startswith("darktunnel://"):
            content = content[len("darktunnel://"):]
        outer = json.loads(base64.b64decode(content).decode())
        result = {"type": outer.get("type", "?"), "name": outer.get("name", "?")}
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


def make_dark_txt(data):
    lines = ["=" * 55, "  DARKTUNNEL - DÉCRYPTÉ EN CLAIR", "=" * 55, ""]
    lines.append(f"Type : {data.get('type')}")
    lines.append(f"Nom  : {data.get('name')}")
    lines.append("")
    config = data.get("Config", {})
    v2ray = config.get("V2RayConfig", {})
    raw = v2ray.get("Config", "")
    if isinstance(raw, dict) or (isinstance(raw, str) and str(raw).startswith("{")):
        try:
            xray = raw if isinstance(raw, dict) else json.loads(raw)
            out = xray.get("outbounds", [{}])[0]
            st = out.get("settings", {}).get("vnext", [{}])[0]
            stream = out.get("streamSettings", {})
            addr, port = st.get("address", "?"), st.get("port", "?")
            uuid = st.get("users", [{}])[0].get("id", "?")
            sni = stream.get("tlsSettings", {}).get("serverName", "")
            host = stream.get("wsSettings", {}).get("headers", {}).get("Host", "")
            path = stream.get("wsSettings", {}).get("path", "")
            lines += ["-" * 40, "RÉSUMÉ VLESS", "-" * 40]
            lines.append(f"Target : {addr}:{port}")
            lines.append(f"UUID   : {uuid}")
            lines.append(f"Path   : {path}")
            lines.append(f"SNI    : {sni}")
            lines.append(f"Host   : {host}")
            lines.append("")
            pe = str(path).replace("/", "%2F")
            lines.append("Lien VLESS :")
            lines.append(f"vless://{uuid}@{addr}:{port}?encryption=none&security=tls&sni={sni}&type=ws&host={host}&path={pe}#{data.get('name')}")
            lines.append("")
        except:
            pass
    lines += ["=" * 55, "STRUCTURE COMPLÈTE", "=" * 55, ""]
    lines.append(json.dumps({
        "type": data.get("type"), "name": data.get("name"),
        "LockedAppConfig": data.get("LockedAppConfig"), "Config": data.get("Config")
    }, indent=2, ensure_ascii=False, default=str))
    lines += ["", "=" * 55, f"  {SIGNATURE}", "=" * 55]
    return "\n".join(lines)


def decrypt_ssc(content):
    try:
        if isinstance(content, bytes):
            text = content.decode("utf-8", errors="ignore").strip()
        else:
            text = str(content).strip()
        if text.lower().startswith("ssc://"):
            text = text[6:][::-1]
        text = "".join(c for c in text if c in "0123456789abcdefABCDEF")
        data = bytes.fromhex(text)
        for key in SSC_KEYS:
            for nlen in [8, 12]:
                try:
                    cipher = ChaCha20.new(key=key, nonce=data[:nlen])
                    pt = cipher.decrypt(data[nlen:])
                    for i, b in enumerate(pt):
                        if b == ord("{"):
                            try:
                                obj = json.loads(pt[i:].decode("utf-8", errors="ignore").split("\x00")[0])
                                return {"ok": True, "data": obj}
                            except:
                                pass
                except:
                    pass
        return {"ok": False, "msg": "SSC : clés non matchées / fichier verrouillé", "size": len(data)}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


def try_netmod(content):
    try:
        if isinstance(content, bytes):
            raw = content.decode("utf-8", errors="ignore").strip()
        else:
            raw = str(content).strip()
        raw = raw.replace("\n", "").replace("\r", "")
        raw += "=" * (-len(raw) % 4)
        ct = base64.b64decode(raw)
        if len(ct) % 16 != 0:
            return {"ok": False, "msg": "NetMod : taille invalide"}
        pt = AES.new(NETMOD_KEY, AES.MODE_ECB).decrypt(ct)
        text = pt.decode("utf-8", errors="replace").strip("\x00")
        if "{" in text or "http" in text.lower() or "ssh" in text.lower():
            return {"ok": True, "data": text}
        return {"ok": False, "msg": "NetMod : décrypté mais illisible (fichier verrouillé ?)"}
    except Exception as e:
        return {"ok": False, "msg": f"NetMod : {e}"}


def detect_format(filename, content):
    name = (filename or "").lower()
    if name.endswith(".dark") or (isinstance(content, (str, bytes)) and b"darktunnel://" in (content if isinstance(content, bytes) else content.encode())):
        return "dark"
    if name.endswith(".ssc"):
        return "ssc"
    if name.endswith(".ehi") or (isinstance(content, bytes) and content[:5] == b"\x00\x03ehi"):
        return "ehi"
    if name.endswith((".npvs", ".npv", ".npv4")) or (isinstance(content, bytes) and content[:4] == b"NPVS"):
        return "npv"
    if name.endswith(".hat"):
        return "hat"
    if name.endswith(".nm"):
        return "nm"
    if name.endswith(".sip"):
        return "sip"
    return "unknown"


def analyze_report(fmt, content, filename):
    info = {
        "ehi": ("HTTP Injector", "Multi-couches (AES+XXTEA+Argon2+ChaCha20) — pas de clé publique simple"),
        "npv": ("NPV Tunnel", "White-box AES — tables propriétaires nécessaires"),
        "hat": ("HA Tunnel Plus", "Chiffrement propriétaire — pas de clé publique"),
        "sip": ("SocksIP Tunnel", "Chiffrement propriétaire — pas de clé publique"),
        "nm": ("NetMod Syna", "AES-ECB clé connue, souvent verrouillé"),
        "unknown": ("Inconnu", "Format non reconnu"),
    }
    app, note = info.get(fmt, info["unknown"])
    lines = [
        f"📁 Fichier : {filename}",
        f"🔎 Format  : {fmt.upper()}",
        f"App       : {app}",
        f"Note      : {note}",
        "",
    ]
    if isinstance(content, bytes):
        lines.append(f"Taille    : {len(content)} octets")
        lines.append(f"Header    : {content[:24].hex()}")
    else:
        lines.append(f"Taille    : {len(str(content))} caractères")
    lines += ["", "=" * 40, f"  {SIGNATURE}", "=" * 40]
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔓 *KCORP Multi Decryptor*\n\n"
        "✅ Décryptage complet :\n"
        "• `.dark` / `darktunnel://`\n\n"
        "⚠️ Tentative / analyse :\n"
        "• `.ssc` `.nm` `.ehi` `.npvs` `.hat` `.sip`\n\n"
        f"_{SIGNATURE}_",
        parse_mode="Markdown",
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return
    filename = doc.file_name or "file"
    await update.message.reply_text("⏳ Traitement...")

    f = await context.bot.get_file(doc.file_id)
    buf = BytesIO()
    await f.download_to_memory(buf)
    content = buf.getvalue()
    fmt = detect_format(filename, content)

    if fmt == "dark":
        data = decrypt_dark(content)
        if "error" in data:
            await update.message.reply_text(f"❌ `{data['error']}`", parse_mode="Markdown")
            return
        txt = make_dark_txt(data)
        await update.message.reply_text(f"```\n{txt[:3500]}\n```", parse_mode="Markdown")
        await update.message.reply_document(
            InputFile(BytesIO(txt.encode()), filename=f"{filename}-decrypted.txt"),
            caption=f"✅ DarkTunnel décrypté\n\n{SIGNATURE}",
        )

    elif fmt == "ssc":
        res = decrypt_ssc(content)
        if res.get("ok"):
            txt = json.dumps(res["data"], indent=2, ensure_ascii=False, default=str)
            await update.message.reply_text(f"```\n{txt[:3500]}\n```", parse_mode="Markdown")
            await update.message.reply_document(
                InputFile(BytesIO(txt.encode()), filename=f"{filename}-decrypted.txt"),
                caption=f"✅ SSC décrypté\n\n{SIGNATURE}",
            )
        else:
            report = f"SSC\n{res.get('msg')}\nTaille: {res.get('size', '?')}\n\n{SIGNATURE}"
            await update.message.reply_text(f"```\n{report}\n```", parse_mode="Markdown")

    elif fmt == "nm":
        res = try_netmod(content)
        if res.get("ok"):
            await update.message.reply_text(f"```\n{res['data'][:3500]}\n```", parse_mode="Markdown")
            await update.message.reply_document(
                InputFile(BytesIO(res["data"].encode()), filename=f"{filename}-decrypted.txt"),
                caption=f"✅ NetMod décrypté\n\n{SIGNATURE}",
            )
        else:
            report = analyze_report("nm", content, filename) + f"\n{res.get('msg')}"
            await update.message.reply_text(f"```\n{report}\n```", parse_mode="Markdown")

    else:
        report = analyze_report(fmt, content, filename)
        await update.message.reply_text(f"```\n{report}\n```", parse_mode="Markdown")
        await update.message.reply_document(
            InputFile(BytesIO(report.encode()), filename=f"{filename}-analyse.txt"),
            caption=f"📄 Analyse {fmt.upper()}\n\n{SIGNATURE}",
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if "darktunnel://" in t.lower():
        data = decrypt_dark(t)
        if "error" in data:
            await update.message.reply_text(f"❌ `{data['error']}`", parse_mode="Markdown")
            return
        txt = make_dark_txt(data)
        await update.message.reply_text(f"```\n{txt[:3500]}\n```", parse_mode="Markdown")
        await update.message.reply_document(
            InputFile(BytesIO(txt.encode()), filename="dark-decrypted.txt"),
            caption=f"✅ DarkTunnel\n\n{SIGNATURE}",
        )
    elif "ssc://" in t.lower():
        res = decrypt_ssc(t)
        if res.get("ok"):
            txt = json.dumps(res["data"], indent=2, ensure_ascii=False, default=str)
            await update.message.reply_text(f"```\n{txt[:3500]}\n```", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ {res.get('msg')}")
    else:
        await update.message.reply_text("Envoie un fichier `.dark` `.ssc` `.ehi` `.npvs` `.hat` `.nm` `.sip`")


def main():
    if not BOT_TOKEN or BOT_TOKEN == "TON_TOKEN_ICI":
        print("❌ BOT_TOKEN manquant")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print(f"🔓 Multi Decryptor démarré... {SIGNATURE}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
