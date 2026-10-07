#!/usr/bin/env bash
# shots.sh <phase> <graphene>: every screen this run compares, before and after, at 80x24 and 120x36
H=$(cd "$(dirname "$0")" && pwd); PH=$1; G=$2; PY=${PY:-python3}  # a python with rich
X="$PY $H/shoot.py $PH $G"
N=${SNAP:?the saved repositories: SNAP=<dir holding s-empty, s0-proposed, s1-signed, …>}
$X $N/s-empty      p00-empty
$X $N/s0-proposed  p01-proposed-subgoal  '/' '~0.6' 'zero-price\r' '\x1b'
$X $N/s0-proposed  p02-proposed-leaf     '/' '~0.6' 'zero-rule\r' '\x1b'
$X $N/s0-proposed  p03-record-leaf       '/' '~0.6' 'xml-wiring\r' '\x1b' '\r' '~1'
$X $N/s0-proposed  p04-help              '/' '~0.6' 'zero-rule\r' '\x1b' '?'
$X $N/s1-signed    p05-subgoal-open      '/' '~0.6' 'xml-source\r' '\x1b'
$X $N/s1-signed    p06-ready-leaf        '/' '~0.6' 'xml-wiring\r' '\x1b'
$X $N/s1-signed    p07-yours             '/' '~0.6' 'n6\r' '\x1b'
$X $N/s2-running   p08-running           '/' '~0.6' 'xml-wiring\r' '\x1b'
$X $N/s2-running   p09-tail              '/' '~0.6' 'xml-wiring\r' '\x1b' 'l'
$X $N/s3-came-back p10-came-back         '/' '~0.6' 'xml-wiring\r' '\x1b'
$X $N/s3-came-back p11-came-back-record  '/' '~0.6' 'xml-wiring\r' '\x1b' '\r' '~1'
$X $N/s5-review    p12-review            '/' '~0.6' 'n6\r' '\x1b'
$X $N/s4-done      p13-done-leaf         '/' '~0.6' 'xml-wiring\r' '\x1b'
$X $N/s4-done      p14-done-record       '/' '~0.6' 'zero-rule\r' '\x1b' '\r' '~1'
$X $N/s1-signed    p15-command-said      ':' '~0.8' 'plan log' '\r' '~1.5'
$X $N/s0-proposed  p16-visual            '/' '~0.6' 'zero-rule\r' '\x1b' 'V' 'j' 'j'
