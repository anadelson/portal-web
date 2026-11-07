#!/usr/bin/env bash
# Diagnóstico SOMENTE LEITURA da VPS para o projeto Portais (Prefeitura, Câmara e gestão de tenants).
# Não instala, não altera e não reinicia nada. Não lê senhas, chaves nem arquivos .env.
# Uso: passe os domínios previstos como argumentos (opcional).
DOMINIOS="$*"
S() { echo; echo "===== $1 ====="; }
R() { "$@" 2>&1 | head -n 60; }
SU() { if sudo -n true 2>/dev/null; then sudo -n "$@" 2>&1 | head -n 60; else echo "(sem sudo sem senha: $*)"; fi; }
S "Data e identificação"; date -Is; hostname; whoami; id
S "Sistema operacional"; R cat /etc/os-release; R uname -a; R uptime
S "CPU e memória"; R nproc; R lscpu | grep -E 'Model name|^CPU\(s\)|Virtualization'; R free -h; R swapon --show
S "Disco"; R df -hT -x tmpfs -x devtmpfs; R lsblk
S "Fuso horário e NTP"; R timedatectl
S "Rede: IPs e rotas"; R ip -br addr; R ip route
S "Portas abertas (escutando)"; SU ss -tulpn || R ss -tuln
S "Firewall"; SU ufw status verbose; SU nft list ruleset | head -n 40; SU iptables -S | head -n 40
S "SSH (configuração efetiva, sem chaves)"; SU sshd -T | grep -Ei '^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|maxauthtries|x11forwarding) '
S "Fail2ban"; SU fail2ban-client status
S "Usuários com shell e grupo sudo"; R awk -F: '$7 ~ /(bash|sh|zsh)$/ {print $1" uid="$3" home="$6}' /etc/passwd; R getent group sudo
S "Docker"; R docker --version; R docker compose version; SU docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'; SU docker volume ls; SU docker network ls
S "Servidores web e proxies"; for b in nginx apache2 httpd caddy traefik; do command -v $b >/dev/null && echo "$b: $(command -v $b)"; done; R systemctl is-active nginx apache2 caddy traefik
S "Bancos de dados"; for b in psql postgres mysql mariadb redis-server mongod; do command -v $b >/dev/null && echo "$b: $(command -v $b)"; done; R systemctl is-active postgresql mysql mariadb redis-server
S "Linguagens"; for b in node npm python3 php java go; do command -v $b >/dev/null && echo "$b: $($b --version 2>&1 | head -n1)"; done
S "Painéis e agentes da hospedagem"; R systemctl list-units --type=service --state=running --no-pager | grep -viE 'systemd|getty|dbus|user@' | head -n 50
S "Serviços que falharam"; R systemctl --failed --no-pager
S "Pasta /opt e /opt/portal_web"; R ls -la /opt; if [ -d /opt/portal_web ]; then R ls -la /opt/portal_web; R du -sh /opt/portal_web; else echo "/opt/portal_web ainda não existe"; fi
S "Tarefas agendadas"; R crontab -l; SU ls /etc/cron.d
S "Atualizações pendentes"; R bash -c 'apt list --upgradable 2>/dev/null | wc -l'; [ -f /var/run/reboot-required ] && echo "REINÍCIO PENDENTE" || echo "sem reinício pendente"
S "Limites"; R ulimit -n; R sysctl vm.swappiness fs.file-max
S "Saída para a internet (necessária para coletores)"; for u in https://borasp.dcfiorilli.com.br:879 https://apidatalake.tesouro.gov.br https://pncp.gov.br https://servicodados.ibge.gov.br https://registry.npmjs.org; do printf '%s -> ' "$u"; curl -s -o /dev/null -m 10 -w '%{http_code}\n' "$u" || echo falhou; done
S "DNS dos domínios previstos"; IPPUB=$(curl -s -m 8 https://api.ipify.org); echo "IP público desta VPS: $IPPUB"; for d in $DOMINIOS; do printf '%s -> ' "$d"; (getent hosts "$d" | awk '{print $1}' | tr '\n' ' '; echo) ; done
S "Fim"; echo "Diagnóstico concluído sem alterações."
