#!/bin/sh
set -eu
export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALL_CLEANUP=1
brew install docker colima
colima start --profile analytics --cpu 2 --memory 4 --disk 20 --vm-type vz --mount-type virtiofs --activate=false
docker --context colima-analytics version
printf '%s\n' 'Runtime ready. Set DOCKER_CONTEXT=colima-analytics in your local .env.'
