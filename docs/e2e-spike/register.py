import base64, hashlib, hmac, json, os, sys, urllib.request
from cryptography.hazmat.primitives import hashes, padding as sympad, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

URL, EMAIL, PW = sys.argv[1], sys.argv[2], sys.argv[3]
ITER = 600000
b64 = lambda b: base64.b64encode(b).decode()
mk = hashlib.pbkdf2_hmac("sha256", PW.encode(), EMAIL.lower().encode(), ITER, 32)
mph = hashlib.pbkdf2_hmac("sha256", mk, PW.encode(), 1, 32)
hk = lambda info: HKDFExpand(hashes.SHA256(), 32, info).derive(mk)
enc_k, mac_k = hk(b"enc"), hk(b"mac")
def encstr(data, ek, mk_):
    iv = os.urandom(16); p = sympad.PKCS7(128).padder(); pt = p.update(data) + p.finalize()
    e = Cipher(algorithms.AES(ek), modes.CBC(iv)).encryptor(); ct = e.update(pt) + e.finalize()
    mac = hmac.new(mk_, iv + ct, hashlib.sha256).digest()
    return f"2.{b64(iv)}|{b64(ct)}|{b64(mac)}"
user_key = os.urandom(64)
protected = encstr(user_key, enc_k, mac_k)
priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pub_der = priv.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
priv_der = priv.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
body = {"email": EMAIL, "name": "e2e", "masterPasswordHash": b64(mph), "masterPasswordHint": None,
        "key": protected, "kdf": 0, "kdfIterations": ITER,
        "keys": {"publicKey": b64(pub_der), "encryptedPrivateKey": encstr(priv_der, user_key[:32], user_key[32:])}}
req = urllib.request.Request(URL + "/identity/accounts/register", json.dumps(body).encode(), {"Content-Type": "application/json"})
print(urllib.request.urlopen(req).status)
