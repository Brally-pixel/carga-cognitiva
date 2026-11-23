#!/usr/bin/env bash
# Simula duas sessões numa pasta temporária.
#
# Sessão 1 reproduz o exemplo da fórmula: 2h30, 12 decisões, 4 trocas com
# pendência, 3 retrabalhos, 800 linhas -> (12 + 8 + 9 + 4) x 1,5 = 49,5 (amarelo).
# Depois de 45 min de pausa, a sessão 2 começa com o residual da primeira,
# recebe uma resposta grande demais e três aprovações rápidas seguidas.
set -euo pipefail

cd "$(dirname "$0")/.."
export CARGA_DIR="$(mktemp -d)"
carga() { python3 -m carga_cognitiva "$@"; }

# ts MINUTOS [SEGUNDOS] -> instante ISO a partir de 09:00 UTC
ts() { printf '2026-11-23T%02d:%02d:%02d+00:00' $((9 + $1 / 60)) $(($1 % 60)) "${2:-0}"; }
hook() { carga hook --agora "$2" <<< "$1"; }

echo "== Sessão 1 =="
minuto=0
decisoes=12
linhas=800
for thread in A B A C A; do
  for _ in 1 2 3 4; do
    args=(--thread "$thread" --agora "$(ts $minuto)")
    if [ "$decisoes" -gt 0 ]; then args+=(--decisao); decisoes=$((decisoes - 1)); fi
    if [ "$linhas" -gt 0 ]; then args+=(--linhas 40); linhas=$((linhas - 40)); fi
    carga registrar "${args[@]}" > /dev/null
    aviso="$(carga alerta --agora "$(ts $minuto)")"
    [ -n "$aviso" ] && echo "[$(ts $minuto)] $aviso"
    minuto=$((minuto + 7))
  done
done

for m in 134 135 136; do
  carga registrar --thread A --retrabalho --agora "$(ts $m)" > /dev/null
done

echo
carga pontuar --agora "$(ts 150)"
carga feedback 3 --demanda 4 --agora "$(ts 151)"

echo
echo "== 45 min de pausa =="
carga pontuar --agora "$(ts 181)"

echo
echo "== Sessão 2 =="
hook '{"thread": "D", "linhas": 450, "decisao": true}' "$(ts 181)"
hook '{"thread": "D", "aprovacao": true}' "$(ts 181 20)"
hook '{"thread": "D", "linhas": 120, "decisao": true}' "$(ts 183)"
hook '{"thread": "D", "aprovacao": true}' "$(ts 183 15)"
hook '{"thread": "D", "linhas": 90, "decisao": true, "concluida": true}' "$(ts 185)"
hook '{"thread": "D", "aprovacao": true}' "$(ts 185 10)"
hook '{"thread": "E", "linhas": 30}' "$(ts 187)"

echo
carga pontuar --agora "$(ts 188)"
echo
carga resumo --agora "$(ts 189)"
