# Your vendor public key (base64url, 32 bytes). Generate the pair once with:
#     python tools/license_tool.py keygen
# Paste the PUBLIC key here before you build/distribute the app. Keep the private key off school servers.
# Production key (2026-10-28): its private half exists only on the production control plane, /etc/stemic/vendor-prod.key.
# A development bench can use its own pair: replace this line locally and `git update-index --skip-worktree` this file.
PUBLIC_KEY = "ryt3MbLgeW8YBgFDXsp_2CWAUl1_Ls14bZMFrD5OxIk"
