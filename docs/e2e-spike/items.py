import base64, hashlib, hmac, json, os, sys, urllib.request, urllib.parse, uuid
from cryptography.hazmat.primitives import hashes, padding as sympad
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
URL, EMAIL, PW, ITER = sys.argv[1], sys.argv[2], sys.argv[3], 600000
b64 = lambda b: base64.b64encode(b).decode()
mk = hashlib.pbkdf2_hmac("sha256", PW.encode(), EMAIL.lower().encode(), ITER, 32)
mph = b64(hashlib.pbkdf2_hmac("sha256", mk, PW.encode(), 1, 32))
hk = lambda info: HKDFExpand(hashes.SHA256(), 32, info).derive(mk)
def post(path, data, headers):
    r = urllib.request.Request(URL + path, data, headers); return json.load(urllib.request.urlopen(r))
tok = post("/identity/connect/token", urllib.parse.urlencode({"grant_type": "password", "username": EMAIL, "password": mph,
    "scope": "api offline_access", "client_id": "cli", "deviceType": 8, "deviceIdentifier": str(uuid.uuid4()), "deviceName": "e2e-seed"}).encode(),
    {"Content-Type": "application/x-www-form-urlencoded"})
def dec(s, ek, mk_):
    _, rest = s.split(".", 1); iv, ct, mac = map(base64.b64decode, rest.split("|"))
    assert hmac.compare_digest(hmac.new(mk_, iv + ct, hashlib.sha256).digest(), mac)
    d = Cipher(algorithms.AES(ek), modes.CBC(iv)).decryptor(); pt = d.update(ct) + d.finalize()
    u = sympad.PKCS7(128).unpadder(); return u.update(pt) + u.finalize()
uk = dec(tok["Key"], hk(b"enc"), hk(b"mac")); EK, MK = uk[:32], uk[32:]
def E(v):
    if v is None: return None
    iv = os.urandom(16); p = sympad.PKCS7(128).padder(); pt = p.update(v.encode()) + p.finalize()
    e = Cipher(algorithms.AES(EK), modes.CBC(iv)).encryptor(); ct = e.update(pt) + e.finalize()
    return f"2.{b64(iv)}|{b64(ct)}|{b64(hmac.new(MK, iv + ct, hashlib.sha256).digest())}"
H = {"Content-Type": "application/json", "Authorization": "Bearer " + tok["access_token"]}
items = [
 {"type": 1, "name": E("Example A"), "notes": E("NOTE-SECRET-123"), "reprompt": 0,
  "login": {"username": E("alice"), "password": E("PW-SECRET-AAA"), "totp": E("JBSWY3DPEHPK3PXP"),
   "uris": [{"uri": E("https://login.example.com/"), "match": None}, {"uri": E("example.org"), "match": 0},
            {"uri": E(r"^https://x\.test/"), "match": 4}, {"uri": E("https://never.example.com"), "match": 5}]},
  "fields": [{"name": E("pin"), "value": E("FIELD-SECRET-9"), "type": 1}, {"name": E("linkuser"), "value": None, "type": 3, "linkedId": 100}]},
 {"type": 1, "name": E("Reprompt R"), "reprompt": 1, "login": {"username": E("rita"), "password": E("PW-SECRET-RRR"), "uris": [{"uri": E("https://r.example.com"), "match": None}]}},
 {"type": 3, "name": E("Card C"), "reprompt": 0, "card": {"cardholderName": E("Al"), "number": E("4111111111111111"), "expMonth": E("1"), "expYear": E("2030"), "code": E("123"), "brand": E("Visa")}},
 {"type": 4, "name": E("Ident I"), "reprompt": 0, "identity": {"firstName": E("Al"), "lastName": E("Ice"), "email": E("a@b.c")}},
]
for it in items: print(post("/api/ciphers", json.dumps(it).encode(), H)["id"])
