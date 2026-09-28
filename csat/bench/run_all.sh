#!/bin/zsh
# 로컬 Jev-like를 하나씩 띄워 전체 문항을 돌리고 내린다. 메모리 때문에 동시에 두 개를 올리지 않는다.
# 사용: csat/bench/run_all.sh <dataset.json> <tag> [system ...]
# 판단 벤치마크(gamebench): GAMEBENCH=1 csat/bench/run_all.sh <items.jsonl> <tag> [system ...]
set -u
REPO=/Users/chenjing/dev/jev
DATASET=$1; TAG=$2; shift 2
if (( $# )); then SYSTEMS=("$@"); else SYSTEMS=(laya kev open-jev semif jevmlx); fi
JL=$HOME/dev/jev-likes
export HF_HUB_OFFLINE=1   # 가중치는 모두 캐시에 있다. 실행 중 원격 revision이 바뀌지 않게 한다
cd $REPO

wait_health() {
  for i in {1..120}; do curl -sf localhost:$1/health >/dev/null && return 0; sleep 5; done
  return 1
}

start() {
  case $1 in
    laya)     $JL/laya/.venv/bin/python csat/bench/shims/laya/serve.py > $LOG/laya.shim.log 2>&1 & ;;
    open-jev) (cd $JL/open-jev && .venv/bin/python $REPO/csat/bench/shims/open-jev/serve.py) > $LOG/open-jev.shim.log 2>&1 & ;;
    semif)    $JL/semif/.venv/bin/python csat/bench/shims/semif/serve.py > $LOG/semif.shim.log 2>&1 & ;;
    jevmlx)   $JL/jevmlx/repo/.venv/bin/python csat/bench/shims/jevmlx/serve.py --port 8802 > $LOG/jevmlx.shim.log 2>&1 & ;;
    kev)
      (cd $JL/kev && src/.venv/bin/python -m kev.serve --run jaredpalmer/kev-9b@2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c \
        --port 18804) > $LOG/kev.serve.log 2>&1 &
      KEV_SERVE=$!
      for i in {1..60}; do grep -q 'Uvicorn running' $LOG/kev.serve.log && break; sleep 5; done
      (cd $JL/kev && src/.venv/bin/python $REPO/csat/bench/shims/kev/serve.py \
        --run jaredpalmer/kev-9b@2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c) > $LOG/kev.shim.log 2>&1 & ;;
  esac
  SHIM=$!
}

if [[ ${GAMEBENCH:-0} == 1 ]]; then
  LOG=$REPO/gamebench/results/$TAG/logs; RUN=(gamebench/run.py --items $DATASET)
else
  LOG=$REPO/csat/bench/results/$TAG/logs; RUN=(csat/bench/run.py --dataset $DATASET)
fi
mkdir -p $LOG
typeset -A PORT; PORT=(laya 8805 kev 8804 open-jev 8801 semif 8803 jevmlx 8802)
for s in $SYSTEMS; do
  echo "$(date '+%F %T') start $s" | tee -a $LOG/run_all.log
  KEV_SERVE=""; start $s
  if wait_health $PORT[$s]; then
    .venv/bin/python $RUN --system $s --tag $TAG >> $LOG/$s.run.log 2>&1
    echo "$(date '+%F %T') done $s: $(tail -1 $LOG/$s.run.log)" | tee -a $LOG/run_all.log
  else
    echo "$(date '+%F %T') FAILED health $s" | tee -a $LOG/run_all.log
  fi
  kill $SHIM ${KEV_SERVE} 2>/dev/null; sleep 10
  pkill -f "shims/$s/serve.py" 2>/dev/null; [[ $s == kev ]] && pkill -f 'kev.serve' 2>/dev/null; sleep 5
done
echo "$(date '+%F %T') all done" | tee -a $LOG/run_all.log
