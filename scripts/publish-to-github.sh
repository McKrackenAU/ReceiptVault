#!/usr/bin/env bash
# Run on a machine where `gh` is logged in to your GitHub account.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
NAME="${1:-receiptvault}"
if ! gh auth status >/dev/null 2>&1; then
  echo "Run: gh auth login"
  exit 1
fi
if gh repo view "$NAME" >/dev/null 2>&1; then
  echo "Repo already exists; pushing main."
  git remote get-url github >/dev/null 2>&1 || git remote add github "$(gh repo view "$NAME" --json url -q .url)"
  git push -u github main
else
  gh repo create "$NAME" --public --source=. --remote=github --push
fi
USER="$(gh api user --jq .login)"
echo "Published. Safer Proxmox install:"
echo "  wget -O /root/install-receiptvault.sh https://raw.githubusercontent.com/${USER}/${NAME}/main/deploy/install-receiptvault.sh"
echo "  less /root/install-receiptvault.sh"
echo "  bash /root/install-receiptvault.sh"
echo "One-liner:"
echo "  bash -c \"\$(wget -qLO - https://raw.githubusercontent.com/${USER}/${NAME}/main/deploy/install-receiptvault.sh)\""
