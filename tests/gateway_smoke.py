"""Docker integration check; local certificates, no ACME or Telegram credentials."""
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.getenv("CAMPUS_TEST_IMAGE", "itmo-campus:ci-check")
NAME = "campus-qa-" + uuid.uuid4().hex[:10]


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], text=True, capture_output=True, timeout=180)
    if check and result.returncode:
        raise RuntimeError(f"docker {args}:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def fixture(code):
    return docker("run", "--rm", "--user", "0", "-v", f"{NAME}:/qa",
                  "-v", f"{ROOT / 'deploy/gateway'}:/examples:ro", IMAGE, "python", "-c", code)


def probe(code):
    return docker("exec", NAME + "-app", "python", "-c", code)


def wait_probe(code, expected=None):
    deadline = time.monotonic() + 30
    last = None
    while time.monotonic() < deadline:
        try:
            result = probe(code)
            if expected is None or result == expected:
                return result
        except RuntimeError as exc:
            last = exc
        time.sleep(0.5)
    raise AssertionError(f"Probe timed out: {last}")


CERTIFICATE = '''
from pathlib import Path
import os, subprocess
root = Path('/qa/certificates/live/campus.flacoo.ru')
root.mkdir(parents=True, exist_ok=True)
subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=campus.flacoo.ru', '-keyout', str(root/'key.next'),
                '-out', str(root/'cert.next')], check=True, capture_output=True)
os.replace(root/'key.next', root/'privkey.pem')
os.replace(root/'cert.next', root/'fullchain.pem')
'''
FINGERPRINT = '''
import hashlib, socket, ssl
with socket.create_connection(('127.0.0.1', 443), timeout=3) as raw:
    with ssl._create_unverified_context().wrap_socket(raw, server_hostname='campus.flacoo.ru') as conn:
        print(hashlib.sha256(conn.getpeercert(binary_form=True)).hexdigest())
'''


def main():
    docker("volume", "create", NAME)
    try:
        fixture('''
from pathlib import Path
root = Path('/qa')
for directory in ('conf', 'acme/.well-known/acme-challenge', 'certificates'):
    (root/directory).mkdir(parents=True, exist_ok=True)
(root/'conf/default.conf').write_text(Path('/examples/http.conf').read_text())
(root/'acme/.well-known/acme-challenge/probe').write_text('acme-ok')
''')
        docker("run", "-d", "--name", NAME + "-nginx",
               "--mount", f"type=volume,source={NAME},target=/qa",
               "-v", f"{ROOT / 'deploy/gateway'}:/scripts:ro",
               "-e", "CERTIFICATE_CHECK_SECONDS=1", "--entrypoint", "/bin/sh", "nginx:1.30", "-c",
               "set -e; mkdir -p /var/www; rm /etc/nginx/conf.d/default.conf; ln -s /qa/conf/default.conf /etc/nginx/conf.d/default.conf; "
               "ln -s /qa/certificates /etc/letsencrypt; ln -s /qa/acme /var/www/acme; exec sh /scripts/nginx.sh")
        docker("run", "-d", "--name", NAME + "-app", "--network", "container:" + NAME + "-nginx",
               IMAGE, "python", "-c",
               "from aiohttp import web; from bot import Bot; from store import Store; "
               "from miniapp import application; "
               "web.run_app(application(Bot(Store(':memory:'), None), 'test-only'),host='0.0.0.0',port=8787)")
        wait_probe("import urllib.request; print(urllib.request.urlopen('http://127.0.0.1/healthz',timeout=3).status)", "200")
        wait_probe("import urllib.request; print(urllib.request.urlopen('http://127.0.0.1/.well-known/acme-challenge/probe',timeout=3).read().decode())", "acme-ok")
        print("HTTP bootstrap and ACME webroot: OK", flush=True)
        fixture(CERTIFICATE)
        fixture("from pathlib import Path; Path('/qa/conf/default.conf').write_text(Path('/examples/http.conf').read_text()+Path('/examples/https.conf').read_text())")
        docker("exec", NAME + "-nginx", "nginx", "-t")
        docker("exec", NAME + "-nginx", "nginx", "-s", "reload")
        wait_probe("import ssl,urllib.request; print(urllib.request.urlopen('https://127.0.0.1/',context=ssl._create_unverified_context(),timeout=3).status)", "200")
        probe('''
import ssl, urllib.request, urllib.error
req=urllib.request.Request('https://127.0.0.1/api/state',data=b'{}',headers={'Content-Type':'application/json'})
try:
    urllib.request.urlopen(req,context=ssl._create_unverified_context(),timeout=3)
except urllib.error.HTTPError as exc:
    assert exc.code == 403, exc.code
else:
    raise AssertionError('Private API accepted an unauthenticated request')
''')
        print("HTTPS proxy and private API: OK", flush=True)
        before = probe(FINGERPRINT)
        fixture(CERTIFICATE)
        expected = fixture("from pathlib import Path; import ssl,hashlib; print(hashlib.sha256(ssl.PEM_cert_to_DER_cert(Path('/qa/certificates/live/campus.flacoo.ru/fullchain.pem').read_text())).hexdigest())")
        assert before != expected
        wait_probe(FINGERPRINT, expected)
        print("Certificate rotation triggers automatic nginx reload: OK", flush=True)
        print(docker("run", "--rm", "certbot/certbot:v5.1.0", "--version"), flush=True)
    finally:
        docker("rm", "-f", NAME + "-app", NAME + "-nginx", check=False)
        docker("volume", "rm", NAME, check=False)


if __name__ == "__main__":
    main()
