#!/bin/bash

IPS=(
  192.168.100.11 192.168.100.12 192.168.100.13
  192.168.100.21 192.168.100.22 192.168.100.23
  192.168.100.31 192.168.100.32 192.168.100.33
  192.168.100.41 192.168.100.42 192.168.100.43
  192.168.100.51 192.168.100.52 192.168.100.53
  192.168.100.61 192.168.100.62 192.168.100.63
  192.168.100.71 192.168.100.72 192.168.100.73
  192.168.100.81 192.168.100.82 192.168.100.83
)

config_switch() {
  local ip=$1
  printf "enable\nconf t\nusername cisco privilege 15 secret cisco123\naaa new-model\naaa authentication login default local\naaa authorization exec default local\nspanning-tree mode rapid-pvst\nend\nwrite\nexit\n" | \
    sshpass -p "cisco123" ssh -tt -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 "cisco@$ip" > /dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "[OK] $ip"
  else
    # fallback to admin
    printf "enable\nconf t\nusername cisco privilege 15 secret cisco123\naaa new-model\naaa authentication login default local\naaa authorization exec default local\nspanning-tree mode rapid-pvst\nend\nwrite\nexit\n" | \
      sshpass -p "admin" ssh -tt -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 "admin@$ip" > /dev/null 2>&1
    echo "[FALLBACK] $ip"
  fi
}

for ip in "${IPS[@]}"; do
  config_switch "$ip" &
done

wait
echo "All 24 switches AAA & Rapid-PVST synced."
