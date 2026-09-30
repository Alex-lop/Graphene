#!/usr/bin/env bash
# Runs check-leaf.sh on every leaf, then the root, one after another, and prints each one's wall time.
# The seeded false leaf (OddFactorThree) is expected to fail.
cd "$(dirname "$0")"
for leaf in PrimeModFour MulOneModFour FactorThreeModFour EuclidModFour NotDvdEuclid DvdFactorial Euclid \
            SetForm Root OddFactorThree; do
  t0=$(date +%s)
  ./check-leaf.sh "$leaf" > "logs/check-$leaf.log" 2>&1
  code=$?
  echo "$leaf exit=$code wall=$(( $(date +%s) - t0 ))s $(date +%T) | $(tail -1 "logs/check-$leaf.log")"
done
