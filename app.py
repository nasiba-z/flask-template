import logging
import urllib.parse
import base64
import json
import os
from flask import Flask, request, abort
from google.cloud import storage

app = Flask(__name__)

# Config
BUCKET = os.environ["OUTPUT_BUCKET"]
CAESAR_SHIFT = int(os.getenv("CAESAR_SHIFT", "13"))
storage_client = storage.Client()


def decrypt_payload(s: str) -> str:
    """Try decoding with Base64, Hex, URL, or ROT-N fallback."""

    # --- Try Base64 ---
    try:
        pad = '=' * (-len(s) % 4)
        raw = base64.b64decode(s + pad)
	decoded = raw.decode("utf-8")
        logging.info(f"[decode] Base64 → {decoded}")
        return decoded
    except Exception:
        logging.debug("[decode] Base64 failed")

    # --- Try Hex ---
    try:
        raw = bytes.fromhex(s)
	decoded = raw.decode("utf-8")
        logging.info(f"[decode] Hex → {decoded}")
        return decoded
    except Exception:
        logging.debug("[decode] Hex failed")

    # --- Try URL decoding ---
    try:
        decoded = urllib.parse.unquote_plus(s)
        if decoded != s:
            logging.info(f"[decode] URL → {decoded}")
            return decoded
    except Exception:
        logging.debug("[decode] URL failed")

    # --- Fallback: ROT-N ---
    def rotN(text, k):
        out = []
        for ch in text:
            if 'a' <= ch <= 'z':
                out.append(chr((ord(ch) - 97 + k) % 26 + 97))
            elif 'A' <= ch <= 'Z':
                out.append(chr((ord(ch) - 65 + k) % 26 + 65))
            else:
                out.append(ch)
        return "".join(out)
    decoded = rotN(s, (26 - CAESAR_SHIFT) % 26)
    logging.info(f"[decode] ROT-{CAESAR_SHIFT} → {decoded}")

    return decoded



def save_to_gcs(filename: str, content: str) -> str:
    bucket = storage_client.bucket(BUCKET)
    blob = bucket.blob(filename)
    blob.upload_from_string(content, content_type="text/plain")
    return f"gs://{BUCKET}/{filename}"


@app.route("/healthz", methods=["GET"])
def health():
    return "ok", 200


@app.route("/pubsub/push", methods=["POST"])
def pubsub_push():
    
   envelope = request.get_json(silent=True)
    if not envelope or "message" not in envelope:
        logging.warning("[pubsub] No Pub/Sub message received")
        abort(400, "No Pub/Sub message received")

    msg = envelope["message"]
    msg_id = msg.get("messageId", "no-id")
    logging.info(f"[pubsub] Received message ID: {msg_id}")

    data_b64 = msg.get("data", "")
    text = ""
    decrypted = None

    if data_b64:
        try:
            # If message.data exists, decode it once and STOP.
            text = base64.b64decode(data_b64 + '=' * (-len(data_b64) % 4)).decode("utf-8")
            decrypted = text
            logging.info(f"[decode] Base64 → {decrypted}")
        except Exception as e:
            logging.warning(f"[decode] Base64 failed for message {msg_id}: {e}")

    if not text:
        text = msg.get("attributes", {}).get("text", "")
        if text:
            decrypted = decrypt_payload(text)

    if not text:
        logging.info(f"[pubsub] Empty message body for {msg_id}")
        return ("", 204)

    if decrypted is None:
        decrypted = text

    filename = f"decrypted_{msg_id}.txt"
    uri = save_to_gcs(filename, decrypted)
    logging.info(f"[pubsub] Saved decrypted message {msg_id} to {uri}")

    return json.dumps({"saved": uri}), 200

# --- extra root routes for convenience ---

@app.route("/", methods=["GET"])
def root():
    return "service up", 200

# Optional: accept POST at "/" and reuse your Pub/Sub logic
@app.route("/", methods=["POST"])
def root_post():
    # If the body is already a Pub/Sub envelope, just reuse the same handler:
    return pubsub_push()

