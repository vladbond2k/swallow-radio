#!/usr/bin/env bash
# Bring up WireGuard from the config text in $WG_CONF. Cleans what copy-paste from a phone tends
# to add (CR, non-breaking/zero-width spaces, spaces around keys) and prints only key *lengths*
# so a broken config can be diagnosed without exposing it. Exits non-zero if the tunnel is not up.
set -euo pipefail
sudo apt-get update -qq && sudo apt-get install -y -qq wireguard-tools resolvconf >/dev/null 2>&1
python3 - <<'PY' | sudo tee /etc/wireguard/wg0.conf >/dev/null
import os, re, sys
text = os.environ["WG_CONF"]
for bad in ("\r", " ", "​", "‌", "‍", "﻿", " "):
    text = text.replace(bad, "\n" if bad == " " else ("" if bad != " " else " "))
out = []
for line in text.split("\n"):
    line = line.strip()
    m = re.match(r"^(\w+)\s*=\s*(.*)$", line)
    if m:
        k, v = m.group(1), m.group(2).strip()
        if k in ("PrivateKey", "PublicKey", "PresharedKey"):
            v = re.sub(r"\s+", "", v)
            print(f"{k}: {len(v)} chars (WireGuard keys are 44)", file=sys.stderr)
        line = f"{k} = {v}"
    if line:
        out.append(line)
print("\n".join(out))
PY
sudo wg-quick up wg0
echo "public IP now: $(curl -s --max-time 10 https://api.ipify.org || echo '?')"
