#!/usr/bin/env bash
# Reproduz o exemplo da fórmula numa pasta temporária:
# 2h30 de sessão, 12 decisões, 4 trocas de thread, 3 retrabalhos, 800 linhas
# -> (12 + 8 + 9 + 4) x 1,5 = 49,5 (amarelo)
set -euo pipefail

cd "$(dirname "$0")/.."
export CARGA_DIR="$(mktemp -d)"
carga() { python3 -m carga_cognitiva "$@"; }

ts() { printf '2026-11-23T%02d:%02d:00+00:00' $((9 + $1 / 60)) $(($1 % 60)); }

minuto=0
decisoes=12
linhas=800
for thread in A B A C A; do
  for _ in 1 2 3 4; do
    args=(--thread "$thread" --agora "$(ts $minuto)")
    if [ "$decisoes" -gt 0 ]; then args+=(--decisao); decisoes=$((decisoes - 1)); fi
    if [ "$linhas" -gt 0 ]; then args+=(--linhas 40); linhas=$((linhas - 40)); fi
    carga registrar "${args[@]}" > /dev/null
    alerta="$(carga alerta --agora "$(ts $minuto)")"
    [ -n "$alerta" ] && echo "[$(ts $minuto)] $alerta"
    minuto=$((minuto + 7))
  done
done

carga registrar --thread A --retrabalho --agora "$(ts 134)" > /dev/null
carga registrar --thread A --retrabalho --agora "$(ts 135)" > /dev/null
carga registrar --thread A --retrabalho --agora "$(ts 136)" > /dev/null

echo
carga pontuar --agora "$(ts 150)"
echo
alerta="$(carga alerta --agora "$(ts 150)")"
echo "${alerta:-sem alerta novo (cooldown)}"
echo
carga feedback 3 --agora "$(ts 151)"
carga resumo --agora "$(ts 152)"
