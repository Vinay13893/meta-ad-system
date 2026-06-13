# One-time helper script to get a Shopify Admin API access token via OAuth.
# Run once, then discard — the token it saves to .env is permanent.
#
# BEFORE running:
#   1. In dev.shopify.com → meta ads system → Configuration (or Overview)
#      - Add redirect URI: http://localhost:3000/callback
#      - Add scopes: read_orders, read_products
#      - Save
#   2. Run: python3 get_shopify_token.py
#   3. Open the URL it prints in your browser (while logged into Shopify store)
#   4. Click Install → token is saved to .env automatically

import hashlib
import hmac
import http.server
import os
import secrets
import threading
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv, set_key

load_dotenv()

SHOP        = os.environ.get("SHOPIFY_SHOP_DOMAIN", "sage-herbal.myshopify.com")
CLIENT_ID   = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SCOPES      = "read_orders,read_products"
REDIRECT_URI = "http://localhost:3000/callback"
PORT        = 3000

_state = secrets.token_hex(16)
_done  = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/callback"):
            self._respond(404, "Not found")
            return

        params = dict(urllib.parse.parse_qsl(parsed.query))
        code  = params.get("code")
        state = params.get("state")
        hmac_param = params.get("hmac", "")

        if state != _state:
            self._respond(400, "State mismatch — possible CSRF. Try again.")
            return

        # Verify HMAC signature from Shopify
        params_for_hmac = {k: v for k, v in params.items() if k != "hmac"}
        message = "&".join(f"{k}={v}" for k, v in sorted(params_for_hmac.items()))
        expected = hmac.new(
            CLIENT_SECRET.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, hmac_param):
            self._respond(400, "HMAC verification failed.")
            return

        # Exchange code for access token
        resp = requests.post(
            f"https://{SHOP}/admin/oauth/access_token",
            json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": code},
        )
        data = resp.json()
        token = data.get("access_token")

        if not token:
            self._respond(500, f"Token exchange failed: {data}")
            return

        # Save to .env
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        set_key(env_path, "SHOPIFY_ADMIN_TOKEN", token)

        self._respond(200, f"Success! Access token saved to .env\n\nToken: {token}\n\nYou can close this tab.")
        print(f"\nShopify access token saved to .env")
        _done.set()

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass  # suppress server log noise


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Missing SHOPIFY_CLIENT_ID or SHOPIFY_CLIENT_SECRET in .env")
        print("Add them from the Dev Dashboard → meta ads system → Settings → Credentials")
        return

    auth_url = (
        f"https://{SHOP}/admin/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&scope={SCOPES}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&state={_state}"
    )

    server = http.server.HTTPServer(("localhost", PORT), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    print(f"Listening on http://localhost:{PORT}")
    print(f"\nOpen this URL in your browser (must be logged into {SHOP}):\n")
    print(auth_url)
    print()

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass  # if browser doesn't open, user opens it manually

    print("Waiting for Shopify to redirect back...")
    _done.wait(timeout=120)
    if not _done.is_set():
        print("Timed out after 2 minutes. Run the script again.")
    server.shutdown()


if __name__ == "__main__":
    main()
