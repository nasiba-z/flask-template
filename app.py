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
    """Try base64 or ROT-N decryption."""
    # Try base64
    try:
        pad = '=' * (-len(s) % 4)
        raw = base64.b64decode(s + pad)
        return raw.decode("utf-8")
    except Exception:
        pass

    # ROT-N
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

    return rotN(s, (26 - CAESAR_SHIFT) % 26)


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
        abort(400, "No Pub/Sub message received")

    msg = envelope["message"]
    data_b64 = msg.get("data", "")
    text = ""
    if data_b64:
        try:
            text = base64.b64decode(data_b64).decode("utf-8")
        except Exception:
            text = ""

    if not text:
        text = msg.get("attributes", {}).get("text", "")

    if not text:
        return ("", 204)

    decrypted = decrypt_payload(text)
    msg_id = msg.get("messageId", "no-id")
    filename = f"decrypted_{msg_id}.txt"
    uri = save_to_gcs(filename, decrypted)

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

